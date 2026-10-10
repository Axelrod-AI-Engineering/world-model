set -e
cd "$(dirname "$0")"
cp annotate2.js annotate3.js
sed -i "" "35s/box-shadow: 3px 4px 0/box-shadow: 2px 3px 0/" annotate3.js
python3 build_ann3.py && python3 build_ann4.py
node -e "new Function(require('fs').readFileSync('annotate4.js','utf8'))" && echo syntax-ok
