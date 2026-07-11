"""
Counts the number of facts in Wikidata 

CC-BY 2026 Fabian M. Suchanek

Call:
  python 08-make-wikidata-statistics.py

Input:
- the Wikidata file, in input-data/wikidata.ttl

Output:
- 08-wikidata-statistics.txt
   
"""

###########################################################################
#           Booting
###########################################################################

import TurtleUtils
import TsvUtils
import Prefixes
import Schema
import sys
import os
from collections import defaultdict
import Evaluator
     
TEST=len(sys.argv)>1 and sys.argv[1]=="--test"     

OUTPUT_FOLDER="test-data/08-make-wikidata-statistics/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/08-make-wikidata-statistics/00-wikidata.ttl" if TEST else "input-data/wikidata.ttl"

class WikidataVisitor:
    """ Will be called in parallel on each Wikidata entity graph """
    def __init__(self, workerId):
        self.resultMap = {
        "numEntities":0,
        "numLabels": 0,
        "numClasses": 0,
        "numFacts": 0,
        "numTypes": 0
        }        
        
    def visit(self, graph): 
        self.resultMap["numEntities"]+=1
        mainEntity=graph.mainSubject()
        myNumLabels=len(graph.objectsOf(mainEntity,Prefixes.schemaName))        
        self.resultMap["numLabels"]+=myNumLabels
        myNumTypes=len(graph.objectsOf(mainEntity,Prefixes.wikidataType))
        self.resultMap["numTypes"]+=myNumTypes
        if Prefixes.wikidataSubClassOf  in graph.predicatesOf(mainEntity):
            self.resultMap["numClasses"]+=1
        self.resultMap["numFacts"]+=sum(len(graph.objectsOf(mainEntity,p)) for p in graph.predicatesOf(mainEntity))-myNumLabels-myNumTypes
        return True
        
    def result(self):
        return self.resultMap

def main():
    with TsvUtils.Timer("Step 08: Creating Wikidata statistics"):
            
        results = TurtleUtils.visitWikidata(WIKIDATA_FILE, WikidataVisitor)

        mergedResults={}
        for result in results:
            for key in result:
                if key not in mergedResults:
                    mergedResults[key]=0
                mergedResults[key]+=result[key]
                
        print("  Writing results...", end="", flush=True)
        with open(OUTPUT_FOLDER+"08-wikidata-statistics.txt", "wt", encoding="UTF-8") as writer:
            writer.write("Wikidata statistics\n\n")
            writer.write("File size: "+str(os.path.getsize(WIKIDATA_FILE)/1024/1024/1024)+" GB\n")
            for key in mergedResults:
                writer.write(key+": "+str(result[key])+"\n")
        print("done")

if __name__ == '__main__':
    main()
    if TEST:
        Evaluator.compare(OUTPUT_FOLDER+"08-wikidata-statistics.txt", OUTPUT_FOLDER+"08-wikidata-statistics-gold.txt")