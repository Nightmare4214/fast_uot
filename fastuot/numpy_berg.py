import numpy as np
from fastuot.numpy_sinkhorn import sinkx, sinky


###############################################################################
# Lambert function
###############################################################################

def init_lambertw(x):
    z0 = np.zeros_like(x)
    z0[x > 1.0] = x[x > 1.0]
    z0[x < -2.0] = np.exp(x[x < -2.0]) * (1.0 - np.exp(x[x < -2.0]))

    def pade(x):
        return x * (3.0 + 6.0 * x + x ** 2.0) / (3.0 + 9.0 * x + 5.0 * x ** 2)

    z0[(x <= 1.0) & (x >= -2.0)] = pade(np.exp(x[(x <= 1.0) & (x >= -2.0)]))
    z0[z0 == 0.0] = 1e-6
    return z0


def log_lambertw(x):
    z = init_lambertw(x)

    def a(w):
        return (w * (np.log(w + 1e-17) + w - x)) / (1 + w)

    def b(w):
        return -1 / (w * (1 + w))

    for i in range(5):
        c = a(z)
        z = np.maximum(
            z - c / (1 - 0.5 * c * b(z)),
            1e-17,
        )
    return z


###############################################################################
# Properties of Berg entropy
###############################################################################


def phis_ent(x, s):
    return -s * (np.exp(-x / s) - 1)


def phis_berg(x, s):
    return - s * np.log(1 - x / s)


def dual_score_ent(f, g, a, b, C, eps, rho, rho2=None):
    if rho2 is None:
        rho2 = rho

    return np.sum(a * phis_berg(f, rho)) + np.sum(b * phis_berg(g, rho2)) \
        + np.sum(a[:, None] * b[None, :]
                 * phis_ent(C - f[:, None] - g[None, :], eps))


def aprox_berg(x, eps, rho):
    delta = (rho / eps) + np.log(rho / eps) - (x / eps)
    return rho - eps * log_lambertw(delta)


def grad_phis_berg(x, s):
    return 1. / (1. - (x / s))


def hess_phis_berg(x, s):
    return 1. / (s * (1. - (x / s)) ** 2)


###############################################################################
# Optimisation of translation invariance
###############################################################################


def grad_invariant(t, f, g, a, b, rho, rho2):
    return np.sum(a * grad_phis_berg(-f - t, rho)) \
        - np.sum(b * grad_phis_berg(-g + t, rho2))


def hess_invariant(t, f, g, a, b, rho, rho2):
    return - np.sum(a * hess_phis_berg(-f - t, rho)) \
        - np.sum(b * hess_phis_berg(-g + t, rho2))


def rescale_berg(f, g, a, b, rho, rho2=None, nits=10, init=0.):
    if rho2 is None:
        rho2 = rho
    t = init
    for k in range(nits):
        grad = grad_invariant(t, f, g, a, b, rho, rho2)
        hess = hess_invariant(t, f, g, a, b, rho, rho2)
        t = t - grad / hess
    return t


###############################################################################
# Sinkhorn loops and G-Sinkhorn
###############################################################################


def f_sinkhorn_loop(f, a, b, C, eps, rho, rho2=None):
    if rho2 is None:
        rho2 = rho
    # Update on G
    g = sinkx(C, f, a, eps)
    g = -aprox_berg(-g, eps, rho2)
    # Update on F
    f = sinky(C, g, b, eps)
    f = -aprox_berg(-f, eps, rho)
    return f, g


###############################################################################
# H-Sinkhorn
###############################################################################

def h_sinkhorn_loop(f, a, b, C, eps, rho, rho2=None, nits=20):
    if rho2 is None:
        rho2 = rho
    t = 0
    # Update on G
    gs = sinkx(C, f, a, eps)
    for it in range(nits):
        g = -aprox_berg(-(gs - t), eps, rho2) + t
        t = rescale_berg(f, g, a, b, rho, rho2, nits=nits, init=t)
    g = -aprox_berg(-(gs - t), eps, rho2) + t

    # Update on F
    fs = sinky(C, g, b, eps)
    for it in range(nits):
        f = -aprox_berg(-(fs + t), eps, rho) - t
        t = rescale_berg(f, g, a, b, rho, rho2, nits=nits, init=t)
    f = -aprox_berg(-(fs + t), eps, rho) - t

    # Update on lambda
    t = rescale_berg(f, g, a, b, rho, rho2)

    return f + t, g - t


def g_sinkhorn_loop(f, g, t, a, b, C, eps, rho, rho2=None):
    if rho2 is None:
        rho2 = rho
    # Update on G
    g = sinkx(C, f, a, eps)
    g = -aprox_berg(-(g - t), eps, rho2)

    t = rescale_berg(f, g, a, b, rho, rho2)

    # Update on F
    f = sinky(C, g, b, eps)
    f = -aprox_berg(-(f + t), eps, rho)

    # Update on lambda
    t = rescale_berg(f, g, a, b, rho, rho2)

    return f, g, t
