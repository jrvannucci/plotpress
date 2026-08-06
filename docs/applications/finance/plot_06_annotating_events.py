"""
Annotating a price series: a single event vs. a whole regime
================================================================

Some things worth marking on a chart belong to one exact point -- an earnings
gap happened on one specific day, at one specific price. Others describe a
whole stretch with no single tick that defines it -- the weeks the market
spent re-rating the stock upward afterward have no one day that *is* the
re-rating.

plotpress's interactive HTML gives each of those its own tool, on the live
copy of this figure below. **Annotate Point** locks a note to the nearest
data point -- pick the tool, click near the gap day, and the note snaps to
that exact close and stays snapped to it through a pan or zoom, the same way
Point Pick's markers do. **Annotate Free** drops a note anywhere on the
figure, including outside any axes -- caption the whole re-rating band, or
the margin, without it pretending to be about one candle.

The static annotation below (drawn with ``ax.annotate()``, the same method
the drawdown example elsewhere in this gallery uses) marks the gap itself,
since that is the one thing about this chart every reader needs to see
without touching anything. Try the live version's two annotate tools for the
kind of note that is yours alone, not the author's.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(7)

DAYS = 90
t = np.arange(DAYS)

# A quiet pre-earnings regime, a one-day gap on the earnings print, then a
# sustained higher drift as the market re-rates the stock upward -- not a
# single day, but the whole stretch after the gap.
GAP_DAY = 35
pre_drift, post_drift = 0.0006, 0.0035
vol = 0.011

drift = np.where(t < GAP_DAY, pre_drift, post_drift)
returns = drift + rng.normal(0.0, vol, DAYS)
returns[GAP_DAY] += 0.085          # the earnings gap itself

price = 62.0 * np.exp(np.cumsum(returns))

fig, ax = plotpress.subplots(figsize=(9, 4.5))
ax.plot(t, price, color="#1f77b4", linewidth=1.3)
ax.axvspan(GAP_DAY, DAYS - 1, color="#2ca02c", alpha=0.08)
ax.annotate(f"earnings gap: +{returns[GAP_DAY] * 100:.0f}% in one day",
            xy=(GAP_DAY, price[GAP_DAY]),
            xytext=(GAP_DAY - 22, price[GAP_DAY] * 1.12),
            arrowprops={"color": "#333333"}, fontsize=9)
ax.set_xlabel("trading day")
ax.set_ylabel("price")
ax.set_title("One event, one point -- one regime, no single point")
fig.tight_layout()
