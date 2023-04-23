'''   Produces a visualization for a taxonomy
      CC-BY Fabian Suchanek
'''

import TurtleUtils
import sys

def dag_to_tikz(dag, root, mappedClasses, file, depth=100):
    """ Converts a dag to TIKZ, written by ChatGPT, 
    *************NOT USED************ """
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
        if depth==0:
            return;
        parentX=30 if y==0 else x
        file.write(node_template.format(node=node if node in mappedClasses else node+"*", x=parentX, y=y, color="red" if node not in mappedClasses and len(dag.get(node,set()))<2 else "black"))
        if node in dag:        
            for child in dag[node]:
                file.write(edge_template.format(frox=parentX, froy=y, tox=x, toy=y-2))
                add_node(child, y-2, depth-1)
        else:
            x+=len(node)/5+1
            
    # Recursively add nodes and edges to the TikZ code starting from the root node
    add_node(root, 0, depth)
    
    # End TikZ code
    file.write("\\end{tikzpicture}\n\\end{document}")

def tree2viz(dag, root, mappedClasses, file, depth=100):
    """ Visualizes a tree """
    file.write("\\documentclass{standalone}\n\\usepackage[linguistics]{forest}\n\\begin{document}\n\\begin{forest}\n")
    def add_node(node, depth):
        nonlocal file
        if depth==0:
            return;
        file.write("[")
        file.write(node)
        if node not in mappedClasses:
            file.write("*")
        if node in dag:           
            for child in dag[node]:
                add_node(child, depth-1)
        file.write("]")
    add_node(root, depth)
    file.write("\\end{forest}\n\\end{document}")

def tree2dir(dag, root, mappedClasses, file, depth=100):
    """ Visualizes a tree """
    file.write("\\documentclass{article}\n\\usepackage{dirtree}\n\\begin{document}\n\\dirtree{%\n")
    def add_node(node, depth, maxDepth):
        nonlocal file
        if depth>maxDepth:
            return;
        file.write("."+str(depth)+" "+node)
        if node not in mappedClasses:
            file.write("$\\dagger$")
        file.write(".\n")
        if node in dag:           
            for child in dag[node]:
                add_node(child, depth+1, maxDepth)
    add_node(root, 1, depth)
    file.write("}\n\\end{document}")


graph={}
mappedClasses=set()

for s, p, o in TurtleUtils.triplesFromTurtleFile("yago-data/01-yago-final-schema.ttl", "Loading taxonomy"):
    s=s[s.find(":")+1:]+("*" if s.startswith("yago:") else "")
    o=o[o.find(":")+1:]+("*" if o.startswith("yago:") else "")
    if p=='ys:fromClass':
        mappedClasses.add(s)
    if p=="rdfs:subClassOf":
        if o not in graph:
            graph[o]={}
        graph[o][s]={}

print("Creating TEX file...", flush=True, end='')
with open("taxonomy/taxonomy.tex", "wt", encoding="UTF-8") as out:
    tree2dir(graph, "Thing", mappedClasses, out)
print("done")