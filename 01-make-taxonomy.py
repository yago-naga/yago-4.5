"""
Creates the YAGO 4 taxonomy from the Wikidata taxonomy

(c) 2021 Fabian M. Suchanek

Call:
  python3 01-make-taxonomy.py

Output:
- The YAGO taxonomy in yago-taxonomy.ttl 
- Unmapped classes (which appear in Wikidata but not in YAGO, and whose instances have to be attached to a superclass in YAGO) in unmapped-classes.ttl

Assumes:
- a folder "input-data" with the hard-coded YAGO top-level taxonomy
  and a wikidata file wikidata.ttl.gz
    
Algorithm:
1) Start with top-level YAGO classes
2) For each YAGO top level class y that is mapped to a Wikidata class w,
   glue the entire subtree of w under y,
   - excluding bad classes
   - skipping over classes that do not have an English Wikipedia page
3) Remove a class and its descendants if it transitively subclasses two disjoint classes
"""

TEST=True
OUTPUT_FOLDER="test-data/01-make-taxonomy/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/01-make-taxonomy/wikidata.ttl" if TEST else "input-data/wikidata.ttl.gz"

###########################################################################
#           Booting
###########################################################################

print("Creating YAGO taxonomy...")
print("  Importing...",end="", flush=True)
from rdflib import URIRef, RDFS, Graph
import utils
import sys
from os.path import exists
print("done")

if not(exists("input-data")):
    print("  'data' folder not found\nfailed")
    exit()

###########################################################################
#           Load YAGO top-level taxonomy and Wikidata taxonomy
###########################################################################

# Load YAGO taxonomy
print("  Loading YAGO taxonomy...", end="", flush=True)
yagoTaxonomy = Graph()
yagoTaxonomy.parse("input-data/bio-schema.ttl", format="turtle")
yagoTaxonomy.parse("input-data/schema.ttl", format="turtle")
yagoTaxonomy.parse("input-data/shapes.ttl", format="turtle")
yagoTaxonomy.parse("input-data/bio-shapes.ttl", format="turtle")
print("done")

# Load Wikidata taxonomy
wikidataTaxonomy = Graph()
wikidataClassesWithWikipediaPage=set()

for graph in utils.readWikidataEntities(WIKIDATA_FILE):
    for s,p,o in graph.triples((None, utils.wikidataSubClassOf, None)):
        wikidataTaxonomy.add((s,RDFS.subClassOf,o))
        for w in graph.subjects(utils.schemaAbout, s):
            if w.startswith("https://en.wikipedia.org/wiki/"):
                wikidataClassesWithWikipediaPage.add(s)

###########################################################################
#           Import Wikidata taxonomy into YAGO taxonomy
###########################################################################

# Classes that will not be added to YAGO, and whose children won't be added either
badClasses = {
    URIRef("http://www.wikidata.org/entity/Q17379835"), # Wikimedia page outside the main knowledge tree
    URIRef("http://www.wikidata.org/entity/Q17442446"), # Wikimedia internal stuff
    URIRef("http://www.wikidata.org/entity/Q4167410"),  # disambiguation page
    URIRef("http://www.wikidata.org/entity/Q13406463"), # list article
    URIRef("http://www.wikidata.org/entity/Q17524420"), # aspect of history
    URIRef("http://www.wikidata.org/entity/Q18340514")  # article about events in a specific year or time period
}


def addSubClasses(lastGoodYagoClass, wikidataClass, unmappedClassesWriter, treated, pathToRoot):
    """Adds the Wikipedia classes to the YAGO taxonomy, excluding bad classes and classes without Wikipedia pages"""
    
    if wikidataClass in badClasses:
        return
    if wikidataClass in pathToRoot:
        return
    if wikidataClass in wikidataClassesWithWikipediaPage:
        yagoTaxonomy.add((wikidataClass, RDFS.subClassOf, lastGoodYagoClass))
        lastGoodYagoClass=wikidataClass
    else:       
        unmappedClassesWriter.write(utils.compress(wikidataClass)+"\trdfs:subClassOf\t"+utils.compress(lastGoodYagoClass)+"\t.\n")
    # "Treated" serves to avoid adding the subclasses again in case of double inheritance
    if wikidataClass in treated:
        return
    treated.add(wikidataClass)
    pathToRoot.append(wikidataClass)
    for subClass in wikidataTaxonomy.subjects(RDFS.subClassOf, wikidataClass):    
        addSubClasses(lastGoodYagoClass, subClass, unmappedClassesWriter, treated, pathToRoot)
    pathToRoot.pop()

print("  Merging Wikidata taxonomy into YAGO taxonomy...", end="", flush=True)
with open(OUTPUT_FOLDER+"unmapped-classes.ttl", "w", encoding="utf=8") as unmappedClassesWriter:
    unmappedClassesWriter.write("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n")
    unmappedClassesWriter.write("@prefix schema: <https://schema.org/> .\n")
    unmappedClassesWriter.write("@prefix wd: <http://www.wikidata.org/entity/> .\n")
    treated=set()
    for s,p,o in yagoTaxonomy.triples((None, utils.fromClass, None)):
        if s!=utils.schemaThing:
            for subclass in wikidataTaxonomy.subjects(RDFS.subClassOf, o):
                addSubClasses(s,subclass, unmappedClassesWriter,treated,[o])
print("done")

###########################################################################
#           Remove classes that subclass two disjoint top-level classes
###########################################################################

def disjoint(disjointTopLevelClass, cls):
    """TRUE if cls is a transitive subclass of a class that is disjoint with disjointTopLevelClass"""
    
    return any(yagoTaxonomy.triples((disjointTopLevelClass, utils.owlDisjointWith, cls))) \
        or any(disjoint(disjointTopLevelClass, superclass) for superclass in yagoTaxonomy.objects(cls, RDFS.subClassOf))

def removeClass(cls):
    """ Removes the class from the YAGO taxonomy """
    
    yagoTaxonomy.remove((cls, RDFS.subClassOf, None))
    for subClass in yagoTaxonomy.subjects(RDFS.subClassOf, cls):
        removeClass(subClass)
    
def checkDisjointness(disjointTopLevelClass, currentClass):
    """ Recursively removes any classes that are disjoint with disjointTopLevelClass, starting with currentClass """
    
    for subClass in yagoTaxonomy.subjects(RDFS.subClassOf, currentClass):        
        for otherSuperclass in yagoTaxonomy.objects(subClass, RDFS.subClassOf):
            if otherSuperclass==currentClass:
                continue
            if disjoint(disjointTopLevelClass, otherSuperclass):
                removeClass(subClass)
        checkDisjointness(disjointTopLevelClass, subClass)

print("  Removing disjoint-inconsistent classes...", end="", flush=True)
for disjointTopLevelClass in yagoTaxonomy.subjects(utils.owlDisjointWith, None):
    checkDisjointness(disjointTopLevelClass, utils.schemaThing)
print("done")

###########################################################################
#           Serialize the result
###########################################################################

print("  Writing taxonomy...", end="", flush=True)
yagoTaxonomy.serialize(destination=(OUTPUT_FOLDER+"yago-taxonomy.ttl"), format="turtle", encoding="UTF-8")
print("done")
print("done")