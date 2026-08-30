# Payment-scope decision: Sur La Table

The clone needs a payment-scope record because task 883 ends with a local booking confirmation. It accepts one opaque `local-sandbox` scenario ID and no payment credentials. Server code derives the USD amount from class price multiplied by party size, then consumes approval and writes the booking in one site-bound SQLite transaction.

`STRIPE_TEST_AUTHORIZED=false` and `LIVE_PAYMENT_AUTHORIZED=false` remain fixed. No real email, payment, reservation, or production request is in scope. Source checkout was inaccessible, so this local contract does not claim source-page visual fidelity.
