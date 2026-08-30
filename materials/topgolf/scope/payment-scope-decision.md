# Payment-scope decision: Topgolf

Task 886 ends with a local reservation confirmation, so the clone needs a payment-scope record. Checkout accepts one opaque `local-sandbox` scenario ID and no payment credentials. Server code derives the $88.00 USD amount from the selected two-hour bay session, consumes approval, increments local bay inventory, and writes the reservation in one site-bound SQLite transaction.

`STRIPE_TEST_AUTHORIZED=false` and `LIVE_PAYMENT_AUTHORIZED=false` remain fixed. No source hold, source booking, real SMS, email, payment, message, or production request is in scope. Source tax, membership fee, final total, and confirmation were unavailable, so the local review discloses those gaps and does not claim source checkout visual fidelity.
