"""
RDF namespace prefixes for YAGO

CC-BY 2022 Fabian M. Suchanek
"""

##########################################################################
#             Prefixes
##########################################################################

# We need these prefixes just to print them into each file. We don't actually use them...

prefixes = {
"yago": "http://yago-knowledge.org/resource/",
"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
"xsd": "http://www.w3.org/2001/XMLSchema#",
"ontolex": "http://www.w3.org/ns/lemon/ontolex#",
"dct": "http://purl.org/dc/terms/",
"rdfs": "http://www.w3.org/2000/01/rdf-schema#",
"owl": "http://www.w3.org/2002/07/owl#",
"wikibase": "http://wikiba.se/ontology#",
"skos": "http://www.w3.org/2004/02/skos/core#",
"schema": "http://schema.org/",
"cc": "http://creativecommons.org/ns#",
"geo": "http://www.opengis.net/ont/geosparql#",
"prov": "http://www.w3.org/ns/prov#",
"wd": "http://www.wikidata.org/entity/",
"data": "https://www.wikidata.org/wiki/Special:EntityData/",
"sh": "http://www.w3.org/ns/shacl#",
"s": "http://www.wikidata.org/entity/statement/",
"ref": "http://www.wikidata.org/reference/",
"v": "http://www.wikidata.org/value/",
"wdt": "http://www.wikidata.org/prop/direct/",
"wpq": "http://www.wikidata.org/prop/quant/",
"wdtn": "http://www.wikidata.org/prop/direct-normalized/",
"p": "http://www.wikidata.org/prop/",
"ps": "http://www.wikidata.org/prop/statement/",
"psv": "http://www.wikidata.org/prop/statement/value/",
"psn": "http://www.wikidata.org/prop/statement/value-normalized/",
"pq": "http://www.wikidata.org/prop/qualifier/",
"pqv": "http://www.wikidata.org/prop/qualifier/value/",
"pqn": "http://www.wikidata.org/prop/qualifier/value-normalized/",
"pr": "http://www.wikidata.org/prop/reference/",
"prv": "http://www.wikidata.org/prop/reference/value/",
"prn": "http://www.wikidata.org/prop/reference/value-normalized/",
"wdno": "http://www.wikidata.org/prop/novalue/",
"ys": "http://yago-knowledge.org/schema#" 
}

##########################################################################
#             Wikidata and schema.org URIs
##########################################################################

xsdAnyURI='xsd:anyURI'

xsdAnytype='xsd:anyType'

xsdDateTime='xsd:dateTime'

xsdString='xsd:string'

rdfLangString='rdf:langString'

rdfType='rdf:type'

rdfsLabel='rdfs:label'

rdfsComment='rdfs:comment'

rdfsClass='rdfs:Class'

rdfsSubClassOf = "rdfs:subClassOf"

wikidataType = "wdt:P31"

wikidataSubClassOf = "wdt:P279"

wikidataParentTaxon = "wdt:P171"

wikidataAnalogousClass = "wdt:P1074"

wikidataDuring = "pq:P585"

wikidataStart = "pq:P580"

wikidataEnd = "pq:P582"

wikidataOccupation = "wdt:P106"

owlDisjointWith = "owl:disjointWith"

schemaTaxon = "schema:Taxon"

schemaName = "schema:name"

schemaDescription = "schema:description"

schemaAbout = "schema:about"

schemaPage = "schema:mainEntityOfPage"

schemaThing = "schema:Thing"

fromClass = "ys:fromClass"

fromProperty = "ys:fromProperty"

shaclPath="sh:path"

shaclNode="sh:class" # Fabian: Changed from sh:node to sh:class on 2024-04-03

shaclMaxCount="sh:maxCount"

shaclUniqueLang="sh:uniqueLang"

shaclDisjoint="sh:disjoint"

shaclDatatype="sh:datatype"

shaclOr="sh:or"

shaclNodeKind="sh:nodeKind"

shaclPattern="sh:pattern"

shaclProperty="sh:property"

shaclNodeShape="sh:NodeShape"