"""
Loading and handling the YAGO schema

CC-BY 2025 Fabian M. Suchanek
"""

import sys
import re
import TurtleUtils
import Prefixes
import itertools

def message(*mess):
    """ Prints a message """
    for m in mess:
        sys.stdout.buffer.write(str(m).encode('utf8'))
        sys.stdout.buffer.write(b" ")
    sys.stdout.buffer.write(b"\n")


def warning(*mess):
    """ Prints a warning """
    sys.stdout.buffer.write(b"    Warning: ")
    message(*mess)

def info(*mess):
    """ Prints an info """
    sys.stdout.buffer.write(b"    Info: ")
    message(*mess)
    
class YagoObject:
    """ Common super class for YAGO properties and YAGO classes"""
    def __init__(self, identifier):
        self.identifier = identifier
        self.labels = set()
        self.comments = set()
    def __eq__(self, other):
        try:
            return other and other.identifier==self.identifier
        except:
            return False
    def __hash__(self):
        try:
            return hash(self.identifier)
        except:
            return 0
    def __lt__(self, other):
        try:
            return self.identifier<other.identifier
        except:
            return False
    def check(self):
        """ Performs simple checks """
        if not TurtleUtils.isEntityWithPrefix(self.identifier):
            warning("YAGO object",self,"has an invalid identifier")
        for s in itertools.chain(self.labels,self.comments):
            if not TurtleUtils.isLiteral(s):
                warning("YAGO object",self,"has an invalid label or comment",s)

def stripPrefix(identifier):
    """ Removes the xyz: prefix"""
    return identifier[identifier.find(':')+1:]
    
class YagoProperty(YagoObject):
    """ Represents a YAGO property with its attibutes"""
    def __init__(self, name):
        super().__init__(name)
        self.objectTypes=set()
        self.subjectTypes=set()
        self.wikidataProperties=set()
        self.maxCount=None
        self.uniqueLang=False
        self.pattern=None   
    
    def check(self):
        """ Performs simple checks """
        super().check()
        if not self.objectTypes:
            warning("Property",self,"has no object types")
        if not self.subjectTypes:
            warning("Property",self,"has no subject types")
        if not self.wikidataProperties:
            warning("Property",self,"has no Wikidata properties")
        if self.maxCount is not None and self.maxCount<1:
            warning("Property",self,"has an invalid max count of",self.maxCount)
        if self.pattern and not TurtleUtils.isRegex(self.pattern):
            warning("Property",self,"has an invalid pattern of",self.pattern)
            
    def __str__(self):
        return self.identifier
    
    def blankNode(self, cls):
        """ Returns a blank node name for this property """
        return "ys:"+stripPrefix(cls)+"_"+stripPrefix(self.identifier)
        
    def writeTo(self, out, cls):
        """ Pretty prints property to output stream """
        out.write(self.blankNode(cls)+"\n")
        out.write("\t\tsh:path "+self.identifier+" ;\n")
        if self.labels:
            out.write("\t\trdfs:label "+", ".join(c for c in self.labels)+" ;\n")        
        if self.comments:
            out.write("\t\trdfs:comment "+", ".join(c for c in self.comments)+" ;\n")        
        if self.uniqueLang:
            out.write("\t\tsh:uniqueLang true ;\n")
        if self.maxCount:
            out.write("\t\tsh:maxCount "+str(self.maxCount)+" ;\n")
        if self.pattern:
            out.write("\t\tsh:pattern \""+self.pattern.replace("\\","\\\\")+"\" ;\n")
        out.write("\t\tys:fromProperty "+", ".join(c for c in self.wikidataProperties)+" ;\n")
        if len(self.objectTypes)>1:
            out.write("\t\tsh:or ([ ")            
            out.write(" ][ ".join("sh:datatype "+p if p.startswith("xsd:") else "sh:class "+p for p in self.objectTypes))
            out.write("]).\n")
        else:
            out.write("".join("\t\tsh:datatype "+p if p.startswith("xsd:") else "\t\tsh:class "+p for p in self.objectTypes)+" .\n")  
    
    def updateFromShacl(self, shaclProperty, entityGraph):
        """ Adds what the SHACL property says to this YAGO property """
        
        # Object types
        self.objectTypes.update(entityGraph.objectsOf(shaclProperty,Prefixes.shaclDatatype))
        self.objectTypes.update(entityGraph.objectsOf(shaclProperty,Prefixes.shaclClass))
        for disjunctionNode in entityGraph.objectsOf(shaclProperty,Prefixes.shaclOr):
            self.objectTypes.update([typ for anon in entityGraph.getList(disjunctionNode) for typ in entityGraph.objectsOf(anon,Prefixes.shaclClass)])
            self.objectTypes.update([typ for anon in entityGraph.getList(disjunctionNode) for typ in entityGraph.objectsOf(anon,Prefixes.shaclDatatype)])
        
        # Labels and comments
        self.labels.update(entityGraph.objectsOf(shaclProperty,Prefixes.rdfsLabel))
        self.comments.update(entityGraph.objectsOf(shaclProperty,Prefixes.rdfsComment))
        
        # Wikidata mappings        
        self.wikidataProperties.update(entityGraph.objectsOf(shaclProperty,Prefixes.fromProperty))
        
        # Unique language and maxCounts
        self.uniqueLang=self.uniqueLang or (shaclProperty,Prefixes.shaclUniqueLang,"true") in entityGraph
        maxCounts=entityGraph.objectsOf(shaclProperty,Prefixes.shaclMaxCount)
        if len(maxCounts)>1:
           warning("Property",self,"has non-unique maxCounts",maxCounts)
        if len(maxCounts)>0:
           try:
               maxCount=int(maxCounts.pop())
               if self.maxCount and self.maxCount!=maxCount:
                  warning("Property",self,"has non-unique maxCounts",maxCount,"and",self.maxCount)
               else:
                  self.maxCount=maxCount
           except:
               warning("Property",self,"has invalid maxCount",maxCounts[0])
        
        # Patterns
        patterns=entityGraph.objectsOf(shaclProperty,Prefixes.shaclPattern)
        if len(patterns)>1:
            warning("Property", self,"has more than one pattern:",patterns)
        if len(patterns)>0:
            compileMe=TurtleUtils.splitLiteral(patterns.pop())[0]
            if self.pattern and self.pattern!=compileMe:
               warning("Property",self,"has different patterns:",self.pattern,"and",compileMe)
            self.pattern=compileMe.replace("\\\\","\\")
                
class YagoClass(YagoObject):
    """ A class of YAGO """
    
    def __init__(self, identifier):
        super().__init__(identifier)
        self.fromClasses=set()
        self.disjointWith=set()
        self.properties=set()
        self.superClasses=set()
    
    def check(self):
        """ Performs some simple checks"""
        super().check()
        if not self.superClasses and self.identifier!=Prefixes.schemaThing and not self.identifier.startswith("rdf:") and not self.identifier.startswith("rdfs:"):
            warning("Class",self,"does not have a super class")
            
    def __str__(self):
        return self.identifier
        
    def writeTo(self,out):
        """ Writes the class to a Turtle file """
        out.write(self.identifier+" a sh:NodeShape ;\n")
        if self.superClasses:
            out.write("\t"+Prefixes.rdfsSubClassOf+" "+", ".join(c.identifier for c in self.superClasses)+" ;\n")
        if self.disjointWith:
            out.write("\t"+Prefixes.owlDisjointWith+" "+", ".join(c.identifier for c in self.disjointWith)+" ;\n")
        if self.labels:
            out.write("\t"+Prefixes.rdfsLabel+" "+", ".join(c for c in self.labels)+" ;\n")        
        if self.comments:
            out.write("\t"+Prefixes.rdfsComment+" "+", ".join(c for c in self.comments)+" ;\n")        
        if self.fromClasses:
            out.write("\t"+Prefixes.fromClass+" "+", ".join(c for c in self.fromClasses)+" ;\n" )
        if self.properties:
            out.write("\tsh:property "+", ".join(p.blankNode(self.identifier) for p in self.properties)+" ;\n")
        out.write("\ta rdfs:Class .\n\n")
        for p in self.properties:
            p.writeTo(out, self.identifier)
        out.write("\n")    
        
    def updateFromShacl(self, entityGraph, yagoSchema):
        """ Adds the properties given by the SHACL property to this class."""
        
        # Labels and comments
        self.labels.update(entityGraph.objectsOf(self.identifier,Prefixes.rdfsLabel))
        self.comments.update(entityGraph.objectsOf(self.identifier,Prefixes.rdfsComment))
        
        # Corresponding Wikidata classes
        self.fromClasses.update(entityGraph.objectsOf(self.identifier, Prefixes.fromClass))
        
        # Disjoint classes
        for c in entityGraph.objectsOf(self.identifier, Prefixes.owlDisjointWith):
            disjointClass=yagoSchema.getClass(c)
            self.disjointWith.add(disjointClass)
            disjointClass.disjointWith.add(self)
        
        # Superclasses
        self.superClasses.update(yagoSchema.getClass(c) for c in entityGraph.objectsOf(self.identifier, Prefixes.rdfsSubClassOf))
        
        # Properties
        for shaclProperty in entityGraph.objectsOf(self.identifier, Prefixes.shaclProperty):
            # Property name
            propertyNames=entityGraph.objectsOf(shaclProperty,Prefixes.shaclPath)
            if len(propertyNames)>1:
                warning("Property",shaclProperty,"has non-unique names",names)
            elif len(propertyNames)==0:
                warning("Property",shaclProperty,"has no name")
                propertyNames=["NONAME"]
            propertyName=propertyNames.pop() 
            yagoProperty=yagoSchema.getProperty(propertyName)
            yagoProperty.subjectTypes.add(self.identifier)
            yagoProperty.updateFromShacl(shaclProperty, entityGraph)
            self.properties.add(yagoProperty)
        
class YagoSchema(object):
    """ The YAGO schema """
    
    def __init__(self, file=None, verbose=True):        
        self.properties={}
        self.wikidataProperties={}
        self.wikidataClasses={}
        self.classes={}
        if file:
            self.addTurtleFile(file, verbose)
    
    def getClass(self, classIdentifier):
        """ Returns a class of that name (creating it if needed)"""
        if not isinstance(classIdentifier,str):
           warning(classIdentifier,"is not a string, but a",type(classIdentifier))
        if classIdentifier not in self.classes:
            self.classes[classIdentifier]=YagoClass(classIdentifier)
        return self.classes[classIdentifier]
    
    def getProperty(self, propertyIdentifier):
        """ Returns a property of that name (creating it if needed)"""
        if propertyIdentifier not in self.properties:
            self.properties[propertyIdentifier]=YagoProperty(propertyIdentifier)
        return self.properties[propertyIdentifier]
        
    def addClass(self, classIdentifier, entityGraph):
        """ Adds a class of the given name from the graph to the schema """        
        yagoClass=self.getClass(classIdentifier)
        yagoClass.updateFromShacl(entityGraph, self)
        # Update Wikidata property mapping
        for yagoProperty in yagoClass.properties:
            for w in yagoProperty.wikidataProperties:
                if w in self.wikidataProperties and self.wikidataProperties[w]!=yagoProperty:
                    warning("Wikidata property",w,"is mapped to two YAGO properties:",id(self.wikidataProperties[w]), "and",id(yagoProperty))
                self.wikidataProperties[w]=yagoProperty
        for wikidataClass in yagoClass.fromClasses:
            if wikidataClass in self.wikidataClasses:
                warning("Wikidata class", wikidataClass, "is mapped to both",yagoClass,"and",self.wikidataClasses[wikidataClass])
            self.wikidataClasses[wikidataClass]=yagoClass
            
    def addTurtleFile(self, yagoSchemaFile, verbose=True):
        """ Loads a Turtle file """
        # Load schema file
        if verbose:
            print("  Loading YAGO Schema...")
            print("    Input file:",yagoSchemaFile)

        entityGraph=TurtleUtils.Graph()
        entityGraph.loadTurtleFile(yagoSchemaFile)
        for (s,p,o) in entityGraph:
            if p==Prefixes.rdfType and o==Prefixes.shaclNodeShape:
                self.addClass(s, entityGraph)
        
        self.check()
        
        if verbose:
            print("    Info:", len(self.properties),"properties")
            print("    Info:", len(self.classes),"classes")
            print("  done")
        
    def __str__(self):
        return("\n".join(str(s) for s in self.properties.values()))        
        
    def writeTo(self,out):
        """ Writes the schema to the stream """
        for clss in self.classes.values():
            clss.writeTo(out)
    
    def writeToFile(self,file):
        """ Writes the schema to a file"""
        with open(file, "wt", encoding="utf-8") as out:
            for p in Prefixes.prefixes:
                out.write("@prefix "+p+": <"+Prefixes.prefixes[p]+"> .\n")
            out.write("\n")    
            self.writeTo(out)
            
    def check(self):
        """ Performs simple checks """
        for c in self.classes.values():
            c.check()
        for p in self.properties.values():
            p.check()
            