"""
Produces statistics about YAGO 4 entities and predicates
   
"""

import sys
import glob
import re
import evaluator
import itertools
import TurtleUtils
import TsvUtils
import random
import os
import Prefixes
from collections import defaultdict

###########################################################################
#           Counting and removing cycles
###########################################################################

yagoTaxonomyUp=defaultdict(set)

def removeCycles(c, classesSeen):
    """ Removes cycles """
    classesSeen.add(c)        
    for s in list(yagoTaxonomyUp.get(c,[])):
        if s in classesSeen:
            yagoTaxonomyUp[c].remove(s)
        removeCycles(s,classesSeen)
        
def removeCycles():
    """ Removes all cycles in the YAGO taxonomy """
    for c in list(yagoTaxonomyUp):
        if len(yagoTaxonomyUp.get(c,[]))>1:
            removeCycles(c,[])

###########################################################################
#           Counting and removing shortcuts
###########################################################################

def removeShortcutParentsOf(startClass, currentClass):
    """ Removes direct superclasses of startClass that are equal to currentClass or its super-classes """
    if currentClass in yagoTaxonomyUp.get(startClass,[]):
        yagoTaxonomyUp[startClass].remove(currentClass)
        # print("   Removing",startClass,"to",currentClass)
        if len(yagoTaxonomyUp[startClass])==1:
            return        
    for s in yagoTaxonomyUp.get(currentClass,[]):
        removeShortcutParentsOf(startClass, s)
        
def removeShortcuts():
    """ Removes all shortcut links in the YAGO taxonomy """
    for c in list(yagoTaxonomyUp):
        if len(yagoTaxonomyUp.get(c,[]))>1:
            for s in list(yagoTaxonomyUp.get(c,[])):
                for ss in yagoTaxonomyUp.get(s,[]):
                    removeShortcutParentsOf(c, ss) 
###########################################################################
#           Retrieving superclasses
###########################################################################

def getSuperClasses(cls, classes, yagoTaxonomyUp, pathsToRoot):
    """Adds all superclasses of a class <cls> (including <cls>) to the set <classes>"""
    classes.add(cls)
    # Make a check before because it's a defaultdict,
    # which would create cls if it's not there
    if cls=="Q35120":
        pathsToRoot[0]+=1
    if cls in yagoTaxonomyUp:
        for sc in yagoTaxonomyUp[cls]:
            getSuperClasses(sc, classes, yagoTaxonomyUp, pathsToRoot)

##########################################################################
#             Main
##########################################################################

with TsvUtils.Timer("Collecting Wikidata statistics"):

    for line in TsvUtils.linesOfFile("/home/infres/bonald/wikidata/subclass.txt", "  Loading Wikidata taxonomy"):
        triple=line.rstrip().split(' ')
        if len(triple)==2:
            yagoTaxonomyUp[triple[0]].add(triple[1])
    
    removeCycles()
    
    before=sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp)
    print("  Taxonomic links before shortcut removal:", before)
    removeShortcuts()
    after=sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp)
    print("  Taxonomic links after shortcut removal:", after)
    print("  Links removed:", before-after)
    
    directClasses=set()
    currentSubject=""
    totalEntities=0
    totalClassesPerInstance=0
    totalPathsToRoot=0
    for line in TsvUtils.linesOfFile("/home/infres/bonald/wikidata/instances_without_scholarly_article.txt", "  Running through Wikidata types"):
        triple=line.rstrip().split(' ')
        if triple[0]==currentSubject:
            directClasses.add(triple[1])
            continue
        totalEntities+=1
        superClasses=set()
        pathsToRoot=[0]
        for c in directClasses:
            getSuperClasses(c, superClasses, yagoTaxonomyUp, pathsToRoot)
        totalClassesPerInstance+=len(superClasses)   
        totalPathsToRoot+=pathsToRoot[0]  
        directClasses=set()
        currentSubject=triple[0]
        directClasses.add(triple[1])
        
    print("  Total entities:", totalEntities)
    print("  Avg paths to root:", totalPathsToRoot/totalEntities)
    print("  Avg classes per instance:", totalClassesPerInstance/totalEntities)
    
    
