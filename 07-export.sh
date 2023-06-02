# Exports YAGO into a ZIP file and to the Web server
# CC-BY 2023 Fabian M. Suchanek
cd yago-data

echo "Creating tiny YAGO..."
date +"  Current time: %F %T"
cp 01-yago-final-schema.ttl yago-tiny.ttl
grep -v -P '@prefix' 05-yago-final-taxonomy.tsv >> yago-tiny.ttl
grep -P 'yago:A[^\t]+\t[^\t]+\t("|yago:A|schema:)' 05-yago-final-wikipedia.tsv >> yago-tiny.ttl
rm yago-tiny.zip
zip yago-tiny.zip yago-tiny.ttl
echo "Done"

echo "Packing YAGO files..."
rm yago.zip
mv 01-yago-final-schema.ttl yago-schema.ttl
mv 05-yago-final-wikipedia.tsv yago-facts.ttl
mv 05-yago-final-beyond-wikipedia.tsv yago-beyond-wikipedia.ttl
mv 05-yago-final-meta.tsv yago-meta-facts.ntx
mv 05-yago-final-taxonomy.tsv yago-taxonomy.ttl
zip yago.zip yago-schema.ttl yago-facts.ttl yago-beyond-wikipedia.ttl yago-meta-facts.ntx yago-taxonomy.ttl
mv yago-schema.ttl 01-yago-final-schema.ttl
mv yago-facts.ttl 05-yago-final-wikipedia.tsv
mv yago-beyond-wikipedia.ttl 05-yago-final-beyond-wikipedia.tsv
mv yago-meta-facts.ntx 05-yago-final-meta.tsv
mv yago-taxonomy.ttl 05-yago-final-taxonomy.tsv
echo "Done"

echo "Copying YAGO file to Web server"
scp yago.zip yago@yago.r2.enst.fr:/data/public/yago4.5/yago-4.5.0.1.zip
scp yago-tiny.zip yago@yago.r2.enst.fr:/data/public/yago4.5/yago-4.5.0.1-tiny.zip
scp 06-upper-taxonomy.html yago@yago.r2.enst.fr:~/website/content/schema.php
echo "Done"
date +"Current time: %F %T"
