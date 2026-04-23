import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # non-interactive backend — required for subprocess
import matplotlib.pyplot as plt

from mcp.server.fastmcp import FastMCP

OUTPUT_DIR = Path("/tmp/charts")
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastMCP("chart_generator")


@app.tool()
def create_line_chart(
    series: list,
    title: str,
    x_label: str = "",
    y_label: str = "",
) -> str:
    """Create a line chart from one or more series. Returns the saved PNG file path.

    Each series is a dict with keys 'x' (list), 'y' (list), and optional 'label' (str).
    """
    path = OUTPUT_DIR / f"{uuid.uuid4()}.png"
    fig, ax = plt.subplots()
    for s in series:
        ax.plot(s["x"], s["y"], label=s.get("label", ""))
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    if len(series) > 1:
        ax.legend()
    fig.savefig(path)
    plt.close(fig)
    return str(path)


@app.tool()
def create_bar_chart(categories: list, values: list, title: str) -> str:
    """Create a bar chart. Returns the saved PNG file path."""
    path = OUTPUT_DIR / f"{uuid.uuid4()}.png"
    fig, ax = plt.subplots()
    ax.bar(categories, values)
    ax.set_title(title)
    fig.savefig(path)
    plt.close(fig)
    return str(path)


if __name__ == "__main__":
    import asyncio
    asyncio.run(app.run_stdio_async())
