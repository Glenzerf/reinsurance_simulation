# Editing the economic model

Edit **market_config.py** before creating a session. Restart the services to load the edited module, then create the new session. A session stores an independent JSON snapshot, schema version, private seed and SHA-256 hash. Existing games read the stored values throughout trading and settlement.

| Setting | Meaning and editing convention |
|---|---|
| PUBLIC | Direct premium, expenses, brokerage, investor ROE target, ordinary required-capital cost, total shortfall cost and maximum insolvency probability. Rates are fractions. Monetary amounts are millions. |
| LOSS | Standard benchmark for annual aggregate losses. Gamma parameters are shape and scale. Pareto is Type I with minimum and shape. Lognormal inputs are arithmetic mean and SD. |
| REALIZATION | Deep copy of LOSS with the instructor overrides. Event and asset draws are unconditional. The classroom uses only this insurance law, independent of private estimates. |
| PUBLIC['assets'] | Annual effective yields, remaining long-bond maturity, discrete yield scenarios with matching probabilities, and arithmetic ETF gross-return moments. At inception the long bond has one more year than its remaining maturity at sale. |
| INSURERS and ROLES | Opening equity in millions and insurer multipliers in A, B, C, D order. Add R3 or B3 to ROLES to create another team of that category. Brokers have zero contributed capital. |
| MANDATES and BELIEFS | Instructor-editable handout text and numerical hard checks or private estimates. Keep text consistent with edited numbers. Public, private and realization sets are separately labeled in the export. |
| PRESETS | List stable role IDs for each session preset. A new key creates an oTree session config at the next startup. Seat capacity is chosen in oTree. Attendance maps available seats to this roster. |
| SEED | None obtains 128 bits of private entropy per session. Set a nonnegative integer for a reproducible rehearsal. Final loss draws depend on the active insurers in stable sorted role-ID order. |
| WEIGHT_TOLERANCE | Absolute tolerance on the sum of decimal weights. Default 1e-8. Accepted vectors are divided by their total so the normalized weights allocate the full account. Contract participation has a strict 100% ceiling. |
| DISPLAY_DECIMALS | Money display precision. Internally the simulation and accounting use binary64. CSV numerics retain round-trip precision. |
| PHASE_MINUTES | Optional positive advisory durations keyed by trade, review or invest. Both desks show a target finish time. The instructor advances phases explicitly. |

### Change attendance

For six insurers, one reinsurer and one broker, choose the six-insurer preset, then assign I1–I6, R1 and B1 to eight occupied slots in any order. Empty slots remain idle. For a recurring third broker, add B3 with capital zero and a private research note, then add B3 to the desired preset. Teams receive only their own mandate, beliefs, capital, exposures, decisions and result. The public role list identifies negotiable counterparties.

### Cash, loss and capital conventions

Treaty premiums, fees and direct business settle at inception. An insurer can retain its entire book. Brokers invest fees even when their opening contributed capital is zero. A one-year insurer with zero trades still receives the direct premium, pays expenses, invests the balance and owes its gross annual claims.

A and C independently compound their respective claim counts and severity samples. Each insurer has its own B event and B severity. One D event and one severity are shared. Multiply the standard aggregate by the insurer's exposure exactly once. A quota share or annual XOL applies to this scaled loss before seller participation. A common rate outcome and ETF payoff determine portfolio gross returns for every team.

At assessment, an external model computes required capital under the appropriate laws, mandate constraints and frozen policies. In all scenario default and recovery calculations preserve original classroom capital. The shortfall is the positive part of required capital less opening capital. The economic charge is ordinary cost × required capital + (total shortfall cost − ordinary cost) × S. Subtract it from accounting profit. The ROE target is a separate reference point. No capital is injected and the charge creates no classroom cash flow. Insurer 3 uses the larger requirement from its two liability models. Insurer 4 must satisfy the ending-equity-floor covenant alongside the ordinary solvency constraint. Soft preferences have no cash effect.

### Persistence and model changes

The snapshot is plain canonical JSON with sorted keys and compact separators. The hash covers seed, roster candidates, private handouts, parameters and runtime versions. Opening attendance and subsequent removals are exported alongside it. A saved snapshot protects against parameter edits; keep the same code and dependency versions when resuming a frozen game. Settled games additionally retain realized severities and all accounting results for replay independent of future random-number implementations.
