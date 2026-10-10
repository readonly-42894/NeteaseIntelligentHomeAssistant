#!/bin/bash
# 提取字段声明（非 static、非方法）
for f in "$@"; do
  echo "### $f"
  grep -nE '^\s*(public|private|protected)\s+' "$f" 2>/dev/null \
    | grep -vE '\bstatic\b' \
    | grep -vE '\(|\)|\bclass\b|\binterface\b|\benum\b|\bnew\b' \
    | grep -E ';' \
    | sed -E 's/^\s*[0-9]+:\s*//' \
    | grep -vE '^\s*(public|private|protected)\s+(Companion|CREATOR|INSTANCE)' \
    | sort -u
  echo ""
done
