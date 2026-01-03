class OrderExecution:
    """
    Simulación didáctica:
      - COMBO: ejecuta call+put "a la vez" -> menor slippage
      - LEGS: ejecuta por separado y el mercado se mueve entre patas
    """
    @staticmethod
    def execute_combo(call_mid, put_mid, slippage=0.0020):
        total = call_mid + put_mid
        return total * (1 + slippage)

    @staticmethod
    def execute_legs(call_mid, put_mid, slippage=0.0035, market_move_std=0.0025):
        # Ejecutas call primero
        call_paid = call_mid * (1 + slippage)
        # Movimiento entre patas (p.ej. 0.25% std)
        move = np.random.normal(0, market_move_std)
        put_mid2 = put_mid * (1 + move)
        put_paid = put_mid2 * (1 + slippage)
        return call_paid + put_paid

    @staticmethod
    def simulate_legging(n=2000, call_mid=5.0, put_mid=5.0, seed=7):
        rng = np.random.default_rng(seed)
        combo = []
        legs = []
        for _ in range(n):
            # usar numpy global, pero fijamos para reproducibilidad
            combo.append(OrderExecution.execute_combo(call_mid, put_mid))
            legs.append(OrderExecution.execute_legs(call_mid, put_mid))
        combo = np.array(combo)
        legs = np.array(legs)
        return combo, legs
