# Labelling a scenario

Each scenario folder holds `script.json` (the scammer lines), `cache/` (the recorded
Groq and Claude answers, written by `scripts/record_cassettes.py --scenario NAME`) and
`expected.json` (the hand labels used by `scripts/evaluate.py`).

A new `expected.json` starts as a template with `"_status": "template"`. The evaluator
skips it until that line is deleted. Fill the values, then remove `_status`.

## Template fields

| Field | What to write |
|---|---|
| `is_scam` | `true` or `false`. `null` means "work it out from scam_type" (any scam_type means a scam). |
| `scam_type` | one word from the scam_type list, or `null` for a call that is not a scam. Always scored: `null` means the extractor must leave it empty. |
| `claimed_organisation` | the organisation name as text, or `null`. It matches if either name contains the other, ignoring case and punctuation ("Kestrel Bank" matches "Kestrel Bank security team"). `null` means not scored. |
| `payment_method` | one word from the payment_method list, or `null` (not scored) |
| `amount` | `{"amount": 4500, "currency": "GBP"}`, or `null` (not scored) |
| `injection_attempt` | `true`, `false`, or `null` (null means none was made, same as false) |
| `identifiers` | list of `{"kind": "...", "value": "..."}`. A pair matches if the kind is equal and, keeping only lowercase letters and digits, one value contains the other. Both must be at least 4 characters. Label just the account number: sort codes are not scored separately (there is no sort_code kind). |
| `pressure_tactics` | list of words from the tactic list |
| `information_requested` | list of words from the information_requested list |

Evidence quotes are not needed in labels. `bank-fraud-01/expected.json` is in the full
dossier shape (each value wrapped as `{"value": ..., "evidence": ...}`); the evaluator
reads both shapes.

## Allowed words (from natter/schema.py)

- **scam_type**: `bank_impersonation`, `tech_support`, `tax_authority`,
  `parcel_delivery`, `other`
- **payment_method**: `bank_transfer`, `gift_cards`, `crypto`, `cash_courier`,
  `card_details`, `remote_access`, `other`
- **pressure_tactics**: `urgency`, `authority`, `fear`, `secrecy`, `isolation`
- **information_requested**: `one_time_code`, `pin`, `full_card_number`, `password`,
  `remote_access`, `date_of_birth`, `other`
- **identifier kinds**: `phone`, `url`, `email`, `account_number`, `alias`,
  `case_reference`

## A call that is not a scam

There is no "not a scam" scam_type. The extractor shows a non-scam call by leaving
`scam_type` empty (`null`). So for `benign-01` write `"is_scam": false` and
`"scam_type": null`, and leave the rest empty.
