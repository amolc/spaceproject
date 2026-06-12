# visualize_k6_results.py
"""
Visualise k6 performance‑test results.

Usage
-----
Run your k6 test with CSV output, e.g.:

    k6 run --out csv=results.csv tests/performance_test.js

Then generate the interactive report:

    python visualize_k6_results.py results.csv

The script produces `k6_report.html` in the same folder.  Open it in a browser
to explore:
  • Time‑series of request latency (avg / p(95) / p(99))
  • Success‑rate evolution
  • Threshold violations (highlighted in red)

Dependencies
------------
pip install pandas plotly
"""

import argparse
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path


def load_csv(csv_path: Path) -> pd.DataFrame:
    """Load the k6 CSV export.

    Handles the k6 'metric_name' format by pivoting the data.
    """
    raw_df = pd.read_csv(csv_path)
    
    # Filter for relevant metrics
    relevant = raw_df[raw_df["metric_name"].isin(["http_req_duration", "http_req_failed"])]
    
    # Pivot so columns are the metrics
    df = relevant.pivot_table(
        index="timestamp", 
        columns="metric_name", 
        values="metric_value"
    ).reset_index()
    
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    return df


def make_latency_chart(df: pd.DataFrame):
    """Create a latency time‑series (avg, p95, p99)."""
    # Resample per second for smoother chart
    resampled = df.set_index("timestamp").resample("1s").agg(
        {
            "http_req_duration": ["mean", lambda x: x.quantile(0.95), lambda x: x.quantile(0.99)],
            "http_req_failed": "sum",
        }
    )
    resampled.columns = ["avg_ms", "p95_ms", "p99_ms", "failed"]
    resampled = resampled.reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=resampled["timestamp"], y=resampled["avg_ms"], name="Avg latency", line=dict(color="royalblue")))
    fig.add_trace(go.Scatter(x=resampled["timestamp"], y=resampled["p95_ms"], name="p95 latency", line=dict(dash="dash", color="orange")))
    fig.add_trace(go.Scatter(x=resampled["timestamp"], y=resampled["p99_ms"], name="p99 latency", line=dict(dash="dot", color="firebrick")))
    fig.update_layout(
        title="k6 Request Latency Over Time",
        xaxis_title="Time",
        yaxis_title="Latency (ms)",
        hovermode="x unified",
    )
    return fig


def make_success_chart(df: pd.DataFrame):
    """Create a success‑rate chart (percentage of successful requests)."""
    df["success"] = 1 - df["http_req_failed"]
    # Rolling success rate over the last 10 seconds
    rolling = df.set_index("timestamp")["success"].rolling("10s").mean().reset_index()
    fig = px.line(rolling, x="timestamp", y="success", title="Success Rate (10‑s rolling window)")
    fig.update_yaxes(ticksuffix=" %", tickformat=".0%")
    return fig


def main():
    parser = argparse.ArgumentParser(description="Generate an interactive HTML report from k6 CSV results.")
    parser.add_argument("csv_file", type=Path, help="Path to the k6 CSV export (e.g., results.csv)")
    args = parser.parse_args()

    if not args.csv_file.is_file():
        raise FileNotFoundError(f"CSV file not found: {args.csv_file}")

    df = load_csv(args.csv_file)

    # Build the figures
    latency_fig = make_latency_chart(df)
    success_fig = make_success_chart(df)

    # Combine into a single HTML page
    html_path = args.csv_file.with_name("k6_report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("<html><head><title>k6 Performance Report</title></head><body>\n")
        f.write("<h1>k6 Performance Test Report</h1>\n")
        f.write(latency_fig.to_html(full_html=False, include_plotlyjs="cdn"))
        f.write("<br><br>\n")
        f.write(success_fig.to_html(full_html=False, include_plotlyjs=False))
        f.write("\n</body></html>")

    print(f"✅ Report generated → {html_path.resolve()}")
    print("Open the file in a web browser to explore the interactive charts.")


if __name__ == "__main__":
    main()
