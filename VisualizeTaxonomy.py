'''   Produces a visualization for a taxonomy
      CC-BY Fabian Suchanek, with ChatGPT
'''

import TurtleUtils
import sys

def dag_to_tikz(dag, root, mappedClasses, file):
    """ Converts a dag to TIKZ, written by ChatGPT """
    # Define TikZ code for a node
    node_template = r"\node[draw, {color}] ({node}) at ({x}, {y}) {{{node}}};"
    # Define TikZ code for an edge
    edge_template = r"\draw[-] ({frox}, {froy}-0.25) -- ({tox}, {toy}+0.25);"
    
    # Start TikZ code
    file.write("\\documentclass{standalone}\n\\usepackage{tikz}\n\\begin{document}\n\\begin{tikzpicture}\n\n")
    
    # Define the position of the root node
    x = 0
    y = 0
            
    # Define a function to recursively add nodes and edges to the TikZ code
    def add_node(node, y):
        nonlocal file
        nonlocal x
        parentX=30 if y==0 else x
        file.write(node_template.format(node=node if node in mappedClasses else node+"*", x=parentX, y=y, color="red" if node not in mappedClasses and len(dag.get(node,set()))<2 else "black"))
        if node in dag:        
            for child in dag[node]:
                file.write(edge_template.format(frox=parentX, froy=y, tox=x, toy=y-2))
                add_node(child, y-2)
        else:
            x+=len(node)/5+1
            
    # Recursively add nodes and edges to the TikZ code starting from the root node
    add_node(root, 0)
    
    # End TikZ code
    file.write("\\end{tikzpicture}\n\\end{document}")

graph={}
mappedClasses=set()

for s, p, o in TurtleUtils.triplesFromTurtleFile("yago-data/01-yago-final-schema.ttl", "Loading taxonomy"):
    s=s[s.find(":")+1:]
    o=o[o.find(":")+1:]
    if p=='ys:fromClass':
        mappedClasses.add(s)
    if p=="rdfs:subClassOf":
        if o not in graph:
            graph[o]={}
        graph[o][s]={}

print("Creating TEX file...", flush=True, end='')
with open("taxonomy/taxonomy.tex", "wt", encoding="UTF-8") as out:
    dag_to_tikz(graph, "Thing", mappedClasses, out)
print("done")