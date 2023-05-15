# Exports YAGO into a ZIP file and to the Web server
# CC-BY 2023 Fabian M. Suchanek
echo "Packing YAGO files..."
date +"  Current time: %F %T"
cd yago-data
rm yago-4.5.0.zip
mv 01-yago-final-schema.ttl yago-schema.ttl
mv 05-yago-final-wikipedia.tsv yago-facts.ttl
mv 05-yago-final-beyond-wikipedia.tsv yago-beyond-wikipedia.ttl
mv 05-yago-final-meta.tsv yago-meta-facts.ntx
mv 05-yago-final-taxonomy.tsv yago-taxonomy.ttl
zip yago-4.5.0.zip yago-schema.ttl yago-facts.ttl yago-beyond-wikipedia.ttl yago-meta-facts.ntx yago-taxonomy.ttl
mv yago-schema.ttl 01-yago-final-schema.ttl
mv yago-facts.ttl 05-yago-final-wikipedia.tsv
mv yago-beyond-wikipedia.ttl 05-yago-final-beyond-wikipedia.tsv
mv yago-meta-facts.ntx 05-yago-final-meta.tsv
mv yago-taxonomy.ttl 05-yago-final-taxonomy.tsv
echo "Done"
echo "Copying YAGO file to Web server"
scp yago-4.5.0.zip yago@yago.r2.enst.fr:/data/public/yago4.5
echo "Done"
date +"Current time: %F %T"
