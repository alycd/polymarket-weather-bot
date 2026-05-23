---
type: "explain"
date: "2026-05-23T13:26:45.412322+00:00"
question: "Explain Pnl"
contributor: "graphify"
source_nodes: ["pnl.py", "compute_pnl_summary()"]
---

# Q: Explain Pnl

## Answer

pnl.py in metrics/ is the PnL module containing compute_pnl_summary(), which calls render_dashboard(), _render_split(), and print_stats() to display profit/loss results, and calls _build_data() in web_dashboard.py to populate the web UI.

## Source Nodes

- pnl.py
- compute_pnl_summary()