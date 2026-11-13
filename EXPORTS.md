# CSV data dictionary

The console serves UTF-8 CSV with a header even when there are no records. Python's CSV writer quotes embedded punctuation and line breaks. Financial amounts are millions. Numeric output uses the round-trip string representation of the stored float. Input probabilities, shares, yields, ROE and weights are decimal fractions. Timestamps are ISO 8601 UTC. Download decisions after freeze; before settlement, the realization and settlement tables contain headers only.

Every table starts with **schema, session, freeze, settlement**. The schema version is 1. Session identifies the market. Freeze and settlement identify committed decision and outcome states and are blank until assigned. After an unlock, archive the old files separately and download again at the new freeze. Within a session, join counterparties on stable role ID and payments on ticket ID. The optional team name is a display field. Names beginning with spreadsheet formula characters receive a leading apostrophe in investments.csv.

| File and row | Fields |
|---|---|
| contracts.csv · one bound participation | id, version identify the signed revision. structure is the insurer-line key. buyer, seller and broker are stable role IDs. line is A–D. kind is QS or XOL. q is the QS fraction. attachment and limit are annual XOL amounts. Unused terms are blank. share is the seller participation. premium is separately negotiated for this ticket. fee is additional buyer-paid brokerage. package identifies all-or-none membership. requires lists other required ticket IDs as JSON. created, updated and bound timestamp the ticket. signatures is JSON mapping each of the three parties to its confirmation time on this row's exact version. |
| investments.csv · one active role | role, role_label, name, slot identify the team, including zero-trade teams. exposure_A through exposure_D are the insurer's private multipliers. Opening and inception columns are defined below. weight_short, weight_long, weight_etf are normalized decimal weights. amount_short, amount_long, amount_etf are inception dollar investments. submitted records final confirmation time. |
| configuration.csv · one typed leaf | set identifies public, private, realization, roster, runtime/precision metadata or attendance. path is a slash-delimited path into the snapshot; array indices are zero based. value_json preserves numbers, strings, booleans and empty collections. unit gives the economic unit or metadata. snapshot_hash repeats the SHA-256 of the complete immutable snapshot. Attendance rows separately describe opened assignments, remaining active slots, removal reasons and whole-book confirmation versions/times. |
| realization.csv · market scalar or insurer-line | record=market uses key and value. Keys are short, long, etf (gross payoffs), yield_end, flood_event (0/1) and flood_severity (standard millions). record=line uses role, line, count, severities (JSON list), standard (sum) and scaled (standard × exposure). For B and D, count is event occurrence. D repeats the same common severity across insurers. |
| settlement.csv · one active role | role plus the inception and ending columns below. ratio and roe are blank when inapplicable. assessment is pending for insurers/reinsurers and exempt for brokers. Required capital, capital deficiency and economic profit await external evaluation. |
| ticket_payments.csv · one bound ticket | id joins contracts. buyer and seller identify the parties. promised is the structure payout times participation. paid is promised times the seller's common payment ratio. |
| contract_history.csv · one attempted action | seq is the ordered database journal sequence, time is UTC, actor is instructor or role@slot, action is the command name, ok is 1 for committed or 0 for rejected. detail is JSON with the command, reason/error or resulting ticket snapshots, book revision and freeze/settlement IDs as applicable. Linked invalidations and expiry appear as ticket snapshots in the triggering row. Sequence numbers may have gaps within a session. |

## Inception and ending columns

| Column | Meaning |
|---|---|
| opening | Original equity contributed; zero for a broker |
| direct, expenses | Direct premium received and positive operating expenses |
| bought, sold | Positive treaty premiums paid and received |
| fees_paid, fees_earned | Positive broker fees paid and earned |
| funds | opening + direct − expenses − bought + sold − fees_paid + fees_earned |
| H, assets, gain | Weighted portfolio gross payoff, funds × H, and assets − funds |
| gross | Sum of the insurer's scaled direct claims |
| promised, paid | Seller's total contractual obligation and actual cash paid |
| promised_in, recovered | Insurer's promised reinsurance and actual incoming cash |
| ratio | Seller's min(1, assets / promised), or 1 for zero obligations |
| policyholders_paid | min(gross, assets + recovered) |
| equity | Signed ending equity; insurer assets + recovered − gross, seller assets − promised, broker assets |
| shortfall | max(−equity, 0), unpaid obligations in the realized year. This column is distinct from post-class capital deficiency. |
| residual | max(equity, 0), the shareholder's residual |
| profit, roe | equity − opening and profit / opening where opening is positive |
| assessment | Status of external economic appraisal |

The native oTree Data export wraps the same records from all sessions in two columns, dataset and row_json. The seven per-session files keep separate headers. Run **reconstruct.py** on one session's downloads for an independent calculation. It uses the stored standard loss aggregates, multipliers, contract terms, original capital, inception flows, terminal yield and ETF outcome. It requires configuration, investments, contracts and realization; when supplied, settlement and ticket_payments provide row-by-row checks.
