# Reinsurance market

One participant link represents one student team. Each session has one oTree Group and one underwriting year. Teams negotiate face to face, record participation tickets, confirm their books, allocate capital and see their own reconciled results. All dollar amounts are in millions.

## Start on your Mac

Use CPython 3.11. The project was exercised with Python 3.11.6, oTree 5.11.1 and NumPy 1.26.1. From the extracted project directory run the following commands.

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run_class.py
```

Enter an instructor password at the terminal prompt. Use that same password on restart. Leave this terminal running. Open [oTree administration](http://127.0.0.1:8000) and [Instructor market desk](http://127.0.0.1:8765) and sign in to both as **admin**. On later launches, activate the environment and run the last command. Ctrl-C stops both services.

The default addresses support a rehearsal on one computer. For class, host oTree behind an HTTPS reverse proxy that forwards WebSockets to its port. Open oTree administration through the student-facing hostname when copying participant links. For a trusted classroom LAN the launcher also accepts `--listen 0.0.0.0:8000`; students need the host computer's accessible hostname or LAN IP. Test one link from a student device. Campus client isolation or a firewall may prevent students from reaching a laptop. The instructor desk always listens on the server's loopback port. For a remote server use a private SSH tunnel, e.g. `ssh -L 8765:127.0.0.1:8765 instructor@class-host`. The launcher targets macOS/Linux.

## Before students arrive

1. Edit **market_config.py** for any economic or roster changes. See [Configuration guide](CONFIGURATION.md).
2. In oTree, choose **Sessions → Create new session**. Choose **Reinsurance • full** for the eight-insurer roster or **Reinsurance • six** for Insurers 1–6. These presets suggest 12 and 10 participant slots respectively. You can set a different capacity when creating a session. The number of logins is fixed at creation. A capacity above attendance is fine. To add logins beyond capacity, create a larger session before starting the exercise.
3. Open that session's **Links** tab. Distribute one unique participant link per present team. The console's slot 1 corresponds to P1 on the oTree link list, irrespective of which team arrives first. Keep each URL private to its team. Reconnection uses the same link, even on another laptop.
4. In the **Instructor market desk**, select the matching session code. Map occupied slots to roles. **Fill in preset order** is a shortcut. Leave absent slots inactive. Check the mapping before **Open trading with these assignments**. Opening freezes the login-to-role mapping and reveals each assigned private sheet. The pre-opening desk explains the post-class capital charge.

## Run the class

| Stage | Instructor action | What teams do |
|---|---|---|
| Trade | Open the market. Use **Refresh market** to check pending and signed tickets. | Read the role sheet. Brokers enter QS or XOL terms and separately negotiated seller premiums. Buyer and seller use **Tickets** to approve the displayed version. Teams can preview pending cash flows and save draft weights. |
| Whole-book review | Choose **Begin whole-book review**. This stops ticket edits. Read the list of outstanding books and any conflicts. | Refresh the desk and inspect **Whole book**. Each active team, including a no-trade team and a broker with no fees, confirms its displayed book and totals. |
| Close | Choose **Bind signed book and expire incomplete offers** and confirm. All signed valid tickets bind in one transaction. Outstanding proposals and rejected offers expire in that recorded close. | Review the bound book. A team with no trades still has its role's ordinary inception cash flows. |
| Invest | Check the roster for outstanding allocations. | Use **Investments** to enter three percentages, including explicit zeros. **Save draft** keeps work. **Submit final allocation** confirms it. All teams submit, including zero-fee brokers. |
| Freeze | Choose **Freeze all decisions**. Download decision and configuration CSVs immediately. | Refresh to see the recorded allocation. |
| Draw | Choose **Draw and settle once** and confirm. This can happen after class. | Revisit the original login and open **Results**. Team assets, losses, recoveries, profit, ROE and unpaid obligations reconcile to the statement. |
| Export | Download the seven named CSVs from the instructor desk. For an alternative combined export, use oTree **Data → market (custom_export) → CSV**. | The external capital assessment stays pending for insurers and reinsurers. Brokers are exempt. |

The refresh buttons deliberately preserve time for private negotiation and reading. Refresh after other teams sign or after an instructor announcement. Each saved action refreshes its sender. If a desk is stale, the server returns the current book and asks the team to review it before resubmitting. Independent teams can confirm books or submit allocations at the same time.

### Resolve exceptions

- **A proposal changes.** Its broker amends its own ticket. A new version needs new counterparty signatures. A change to linked package terms clears affected approvals, and the next review uses a new whole-book version. Rejection ends the current offer until amendment. Withdrawal retains the ticket and its history.
- **A split conflicts.** Split participants must share the same insurer, line and structure terms. Fractions can sum to at most one. Funding and placement are checked when the last counterparty signs and again at close. Reduce the premium, withdraw an alternative or amend the relevant share.
- **A package cannot complete.** A shared package ID means all tickets with that ID must bind together. Required IDs express additional directed dependencies. A withdrawn member still identifies the failed package. To renegotiate the surviving trade, amend the remaining tickets with new package terms, collect signatures and review again.
- **A team leaves.** A disconnected team can reconnect and continue. To remove an active team before close, select it and enter a reason. Removal invalidates its provisional tickets, clears linked approvals, reopens trading and clears whole-book confirmations. Review the affected statuses and acknowledge the removal. Resolve any remaining package conditions. The last active team of a role must stay. The console preserves the original roster, removal and action history. After close, the bound counterparties are fixed.
- **Someone is missing at review or investment.** The console identifies the outstanding teams. A missing signature or investment prevents the applicable transition. Before close you can reopen trading or remove a team as above. After close the team must return and submit its own allocation.
- **A frozen allocation needs correction.** Before the draw, enter a reason and choose **Unlock and clear investment confirmations**. All allocations remain available as drafts. Every active team must resubmit and the next freeze gets a fresh ID. The old freeze is visible in history. Settlement is final.

## Browser rehearsal on the classroom host

Use a fresh test session with five slots and the six-insurer preset. Open the instructor desk and three participant tabs. Carry out these steps using the buttons above.

1. Assign P2 to I3, P3 to B2 and P5 to R1. Leave P1 and P4 unused. Verify I3 sees its two liability SD checks, B2 sees its claims survey and P1 sees an inactive desk.
2. Have B2 enter line C, QS fraction 0.4, participation 1, and premium 12. Have I3 approve. Change the premium to 11, refresh I3 and check that the approval disappeared. Set it back to 12 and obtain both approvals on the final version.
3. Review all three books. I3 should have 422.76 to invest, R1 should have 612 and B2 should have 0.24. The fee belongs to B2. Reopen one participant's URL to check persistence.
4. Close, then have all three teams submit 40%, 30%, 30%. Freeze. Download investments and contracts before drawing. B2's dollar allocations should be 0.096, 0.072 and 0.072.
5. Settle. Refresh twice and verify the settlement ID stays the same. Download all CSVs to one folder and run `python reconstruct.py /path/to/csvs`. It independently checks the accounts and reports mismatches.

## Verification and persistence

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
python tests/rehearse.py
```

The first command installs the pinned test client. The unit and transaction suite includes competing requests on separate database connections, abrupt process exit during settlement, deterministic retry, common shocks, independent wildfires, funding, package invalidation and offline distribution checks. The rehearsal script copies source into a temporary directory, creates both presets, signs into oTree, traverses five genuine participant links, uses the live WebSocket route, submits decisions through the authenticated instructor service, downloads both export formats and reopens the settlement in a fresh Python process. It uses in-process HTTP and WebSocket transports. The GUI walkthrough above remains a separate classroom-host check.

The supported deployment is one host with a persistent local filesystem. oTree owns participant records in its database. The market uses Python's SQLite API and a separate durable transaction journal in `market.sqlite3`. Both services must use the same journal. A session stores its snapshot, seed and one decision state; each successful or rejected command appends an audit event. A write lock serializes validation and commit. A failure before commit leaves the original frozen state intact. A retry uses the same seed. A failure after commit returns the already-settled state on refresh.

For backup or transfer, stop both services and copy the whole working project, including `db.sqlite3`, `market.sqlite3` and the privately generated `.classroom-key`. Keep the same password and source version when resuming. Archive CSVs per freeze/session. This two-service deployment assumes local persistent storage; ephemeral multi-host deployment would require a shared transactional persistence implementation.

## Project map

| File | Responsibility |
|---|---|
| market_config.py | All economic parameters, beliefs, mandates, roster presets and snapshot validation |
| market/__init__.py and market/Desk.html | Modern no-self models, callbacks, private live desk and native custom export |
| ledger.py | Permission checks, ticket versions, phase transitions, durable state and audit |
| economics.py | Losses, gross asset payoffs, inception cash and default waterfall |
| instructor.py and instructor.html | Authenticated loopback console and individual CSV downloads |
| _static/market/ | Team and instructor interface, private book views and display formatting |
| exports.py and EXPORTS.md | CSV schemas, columns, units and join keys |
| reconstruct.py | Standalone standard-library CSV settlement replay |
| tests/ | Automated transaction, economic and application entry-point rehearsals |

The implementation uses the documented oTree [no-self structure](https://otree.readthedocs.io/en/latest/misc/noself.html), [live pages](https://otree.readthedocs.io/en/latest/live.html), and [administration and custom data exports](https://otree.readthedocs.io/en/latest/admin.html).
# reinsurance_simulation
# reinsurance_simulation
