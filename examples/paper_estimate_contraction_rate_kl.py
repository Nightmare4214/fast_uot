import numpy as np
import matplotlib.pyplot as plt
import os

from utils_examples import generate_synthetic_measure

path = os.getcwd() + "/output/"
if not os.path.isdir(path):
    os.mkdir(path)
if not os.path.isdir(path + "/paper/"):
    os.mkdir(path + "/paper/")
if not os.path.isdir(path + "/cvrate/"):
    os.mkdir(path + "/cvrate/")

# TODO: refactor as in berg
rc = {"pdf.fonttype": 42, 'text.usetex': True, 'text.latex.preview': True,
      'text.latex.preamble': [r'\usepackage{amsmath}',
                              r'\usepackage{amssymb}']}
plt.rcParams.update(rc)


def load_wot_data():
    import wot
    import pandas as pd

    gene_set_scores = pd.read_csv('data/gene_set_scores.csv', index_col=0)
    proliferation = gene_set_scores['Cell.cycle']
    apoptosis = gene_set_scores['Apoptosis']

    # apply logistic function to transform to birth rate and death rate
    def logistic(x, L, k, x0=0):
        f = L / (1 + np.exp(-k * (x - x0)))
        return f

    def gen_logistic(p, beta_max, beta_min, pmax, pmin, center, width):
        return beta_min + logistic(p, L=beta_max - beta_min, k=4 / width,
                                   x0=center)

    def beta(p, beta_max=1.7, beta_min=0.3, pmax=1.0, pmin=-0.5, center=0.25):
        return gen_logistic(p, beta_max, beta_min, pmax, pmin, center,
                            width=0.5)

    def delta(a, delta_max=1.7, delta_min=0.3, amax=0.5, amin=-0.4,
              center=0.1):
        return gen_logistic(a, delta_max, delta_min, amax, amin, center,
                            width=0.2)

    birth = beta(proliferation)
    death = delta(apoptosis)

    # growth rate is given by
    gr = np.exp(birth - death)
    growth_rates_df = pd.DataFrame(index=gene_set_scores.index,
                                   data={'cell_growth_rate': gr})
    growth_rates_df.to_csv('data/growth_gs_init.txt')

    VAR_GENE_DS_PATH = 'data/ExprMatrix.var.genes.h5ad'
    CELL_DAYS_PATH = 'data/cell_days.txt'
    SERUM_CELL_IDS_PATH = 'data/serum_cell_ids.txt'
    CELL_GROWTH_PATH = 'data/growth_gs_init.txt'

    # load data
    adata = wot.io.read_dataset(VAR_GENE_DS_PATH,
                                obs=[CELL_DAYS_PATH, CELL_GROWTH_PATH],
                                obs_filter=SERUM_CELL_IDS_PATH)
    # print(adata.shape)
    # print(type(adata))
    # print(adata)
    # print(adata.X[0])
    ot_model = wot.ot.OTModel(adata, epsilon=0.05, lambda1=1, lambda2=50)
    t0, t1 = 7, 8
    ds = ot_model.matrix

    p0_indices = ds.obs[ot_model.day_field] == float(t0)
    p1_indices = ds.obs[ot_model.day_field] == float(t1)

    p0 = ds[p0_indices, :]
    p1 = ds[p1_indices, :]
    local_pca = ot_model.ot_config.pop('local_pca', None)
    eigenvals = None
    if local_pca is not None and local_pca > 0:
        # pca, mean = wot.ot.get_pca(local_pca, p0.X, p1.X)
        # p0_x = wot.ot.pca_transform(pca, mean, p0.X)
        # p1_x = wot.ot.pca_transform(pca, mean, p1.X)
        p0_x, p1_x, pca, mean = wot.ot.compute_pca(p0.X, p1.X, local_pca)
        eigenvals = np.diag(pca.singular_values_)
    else:
        p0_x = p0.X
        p1_x = p1.X
    C = ot_model.compute_default_cost_matrix(p0_x, p1_x, eigenvals)
    a, b = np.ones(C.shape[0]) / C.shape[0], np.ones(C.shape[1]) / C.shape[1]
    return a, b, C

if __name__ == '__main__':
    compute_data = True # If false then load precomputed results and plots
    wot_data = False # If true uses the WOT package biological data
    
    marginal_penalty_l = ['kl', 'berg']
    penalty = marginal_penalty_l[0]
    if penalty == 'kl':
        from fastuot.numpy_sinkhorn import f_sinkhorn_loop, g_sinkhorn_loop, \
            h_sinkhorn_loop
        from fastuot.uot1d import rescale_potentials
    elif penalty == 'berg':
        from fastuot.numpy_berg import f_sinkhorn_loop, g_sinkhorn_loop, \
            h_sinkhorn_loop
    else:
        raise Exception('Only accepted penalties are KL and Berg.')
    
    # load data for computations
    if wot_data:
        a, b, C = load_wot_data()
        dataname = 'wot'
    else:
        N = 50
        a, x, b, y = generate_synthetic_measure(N, N)
        C = (x[:, None] - y[None, :]) ** 2
        dataname = 'synth'
    
    # Grid of parameters for Sinkhorn algorithm
    eps_l = [-1., 0.]
    rho_scale = np.arange(-3., 3.5, 0.5)
    string_method = ['f', 'g', 'h']
    func_method = [f_sinkhorn_loop, g_sinkhorn_loop, h_sinkhorn_loop]

    ###########################################################################
    # Generate data plots
    ###########################################################################
    if compute_data:
        np.save(path + "/cvrate/" + f"rho_scale.npy", rho_scale)
        for r in range(len(eps_l)):
            epst = 10 ** eps_l[r]
            rate = [[], [], []]
            for s in rho_scale:
                rhot = 10 ** s
                print(f"(eps, rho) = {(epst, rhot)}")

                # Compute reference
                fr, gr = np.zeros_like(a), np.zeros_like(b)
                for i in range(50000):
                    f_tmp = fr.copy()
                    fr, gr = h_sinkhorn_loop(fr, a, b, C, epst, rhot)
                    # t = rescale_potentials(fr, gr, a, b, rhot)
                    # fr, gr = fr + t, gr - t
                    if np.amax(np.abs(fr - f_tmp)) < 1e-15:
                        break

                # Compute error and estimate rate
                for k, (s, loop) in enumerate(zip(string_method, func_method)):
                    err = []
                    f, g = np.zeros_like(a), np.zeros_like(b)
                    for i in range(2000):
                        f_tmp = f.copy()
                        f, g = loop(f, a, b, C, epst, rhot)
                        # if s == 'h': # potential invariant for H-sinkhorn
                        #     t = rescale_potentials(f, g, a, b, rhot)
                        #     f, g = f + t, g - t

                        err.append(np.amax(np.abs(f - fr)))
                        if np.amax(np.abs(f - fr)) < 1e-12:
                            break
                    err = np.log10(np.array(err))
                    err = err[1:] - err[:-1]
                    rate[k].append(np.median(err))

            for k, (s, loop) in enumerate(zip(string_method, func_method)):
                np.save(
                    path + "/cvrate/" + "rate_" + s + f"_sinkhorn_{penalty}_eps{epst}_{dataname}.npy",
                    np.array(rate[k]))


    ###########################################################################
    # Make plots
    ###########################################################################
    p = 0.97
    colors = ['cornflowerblue', 'indianred']
    markers = ['x', 'o', 'v']
    linestyles = ['dotted', 'dashed', 'solid']
    labels = ['$\mathcal{F},\,\epsilon=$', '$\mathcal{G},\,\epsilon=$',
              '$\mathcal{H},\,\epsilon=$']
    markevery = 2
    f, ax = plt.subplots(1, 1, figsize=(p * 5, p * 4))

    rho_scale = 10 ** np.load(path + "/cvrate/" + f"rho_scale.npy")

    for logeps, color in zip(eps_l, colors):
        epst = 10 ** logeps
        for marker, linestyle, label, s in zip(markers, linestyles, labels, string_method):
            rate_f = np.load(
                path + "/cvrate/" + f"rate_" + s + f"_sinkhorn_{penalty}_eps{epst}_{dataname}.npy")
            ax.plot(rho_scale, 10 ** rate_f, c=color, linestyle=linestyle,
                    label=label + f' {epst}',
                    marker=marker, markevery=markevery)

    ax.legend(fontsize=11, ncol=2, columnspacing=0.5, handlelength=1.3,
              loc=(.4, .02))

    ax.grid()
    ax.set_yscale('log')
    ax.set_xscale('log')
    ax.set_ylim([1e-6, 1.5])
    ax.set_xlabel('Marginal parameter $\\rho$', fontsize=15)
    if penalty == 'kl':
        ax.set_title('KL entropy', fontsize=18)
    if penalty == 'berg':
        ax.set_title('Berg entropy', fontsize=18)
    ax.set_ylabel('Contraction rate', fontsize=15)

    plt.tight_layout()
    plt.savefig(path + "/paper/" + f'plot_log_contraction_rate_{penalty}_{dataname}.pdf')
    plt.show()
