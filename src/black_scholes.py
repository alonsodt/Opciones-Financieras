class BlackScholesOption:
    """Precio y griegas (europeas) bajo Black-Scholes con dividend yield q (opcional)."""

    def __init__(self, S, K, T, r, sigma, option_type="call", q=0.0):
        self.S = float(S)
        self.K = float(K)
        self.T = max(float(T), 1e-9)
        self.r = float(r)
        self.q = float(q)
        self.sigma = max(float(sigma), 1e-9)
        self.option_type = option_type.lower()

    def _d1(self):
        return (np.log(self.S / self.K) + (self.r - self.q + 0.5 * self.sigma**2) * self.T) / (self.sigma * np.sqrt(self.T))

    def _d2(self):
        return self._d1() - self.sigma * np.sqrt(self.T)

    def price(self):
        d1 = self._d1()
        d2 = self._d2()

        disc_r = np.exp(-self.r * self.T)
        disc_q = np.exp(-self.q * self.T)

        if self.option_type == "call":
            return self.S * disc_q * norm.cdf(d1) - self.K * disc_r * norm.cdf(d2)
        else:
            return self.K * disc_r * norm.cdf(-d2) - self.S * disc_q * norm.cdf(-d1)

    def delta(self):
        d1 = self._d1()
        disc_q = np.exp(-self.q * self.T)
        if self.option_type == "call":
            return disc_q * norm.cdf(d1)
        else:
            return disc_q * (norm.cdf(d1) - 1.0)

    def gamma(self):
        d1 = self._d1()
        disc_q = np.exp(-self.q * self.T)
        return disc_q * norm.pdf(d1) / (self.S * self.sigma * np.sqrt(self.T))

    def vega(self):
        d1 = self._d1()
        disc_q = np.exp(-self.q * self.T)
        # vega por 1% (0.01) de cambio en sigma
        return disc_q * self.S * norm.pdf(d1) * np.sqrt(self.T) / 100.0

    def theta(self):
        d1 = self._d1()
        d2 = self._d2()
        disc_r = np.exp(-self.r * self.T)
        disc_q = np.exp(-self.q * self.T)

        term1 = - (self.S * disc_q * norm.pdf(d1) * self.sigma) / (2 * np.sqrt(self.T))

        if self.option_type == "call":
            term2 = self.q * self.S * disc_q * norm.cdf(d1)
            term3 = - self.r * self.K * disc_r * norm.cdf(d2)
            theta = term1 + term2 + term3
        else:
            term2 = - self.q * self.S * disc_q * norm.cdf(-d1)
            term3 = + self.r * self.K * disc_r * norm.cdf(-d2)
            theta = term1 + term2 + term3

        # theta por día
        return theta / 365.0
