"""
Pie chart
=========
"""
import plotpress

fig, ax = plotpress.subplots()
ax.pie([35, 25, 20, 20], labels=["A", "B", "C", "D"])
ax.set_title("Pie chart")
