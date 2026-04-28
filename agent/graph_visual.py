from hackstorm_AI.agent.graph import app
png_bytes = app.get_graph().draw_mermaid_png()

with open("graph.png", "wb") as f:
    f.write(png_bytes)

print("Graph saved as graph.png.")

