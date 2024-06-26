#!/bin/bash

# take language from the first argument
lang=$1
shift # remove the first argument

if [[ $lang != "py" && $lang != "ts" ]]; then
  echo "Unknown language '$lang'"
  exit 1
fi

# join the remaining arguments with hyphens, remove dots, convert to lower case
p_name=p-$(echo "$@" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-')
# pad numbers with zeroes
num=$(echo "$p_name" | grep -o -E '[0-9]+')
if [ -n "$num" ]; then
    padded_num=$(printf "%04d" "$num")
    p_name="${p_name//$num/$padded_num}"
fi

git stash
git fetch origin main:main
git stash pop

branch_name=feat/$p_name
if git show-ref --quiet refs/heads/$branch_name; then
  echo "Branch $branch_name already exists"
  exit 1
else
  git checkout -b $branch_name main
fi

p_name=${p_name//-/_} # replace all the - with _

if [ $lang == "py" ]; then

  dir_path=src/python/$p_name
  if [ -d $dir_path ]; then
    echo "Directory $dir_path already exists"
    exit 1
  else
    mkdir -p $dir_path
  fi

  file_path=$dir_path/$p_name.py
  if [ -f $file_path ]; then
    echo "File $file_path already exists"
    exit 1
  else
    echo "from typing import List


class Solution:
    ''' time: O(n), space: O(n) '''
    " >$file_path
  fi

  test_file_path=$dir_path/test_$p_name.py
  if [ -f $test_file_path ]; then
    echo "File $test_file_path already exists"
    exit 1
  else
    echo "from $p_name import Solution


solution = Solution()


def test_$p_name():
    assert solution.main() ==" >$test_file_path
    echo "Success!"
  fi

elif [ $lang == "ts" ]; then
  dir_path=src/typescript/$p_name
  if [ -d $dir_path ]; then
    echo "Directory $dir_path already exists"
    exit 1
  else
    mkdir -p $dir_path
  fi

  file_path=$dir_path/$p_name.ts
  p_name_camel=$(printf "%s\n" "$p_name" | awk 'BEGIN{FS="_"} {for(i=1; i<=NF; i++) {if(i>1) printf "%s", toupper(substr($i,1,1)) substr($i,2); else printf "%s", $i}} END{print ""}' )


  if [ -f $file_path ]; then
    echo "File $file_path already exists"
    exit 1
  else
    echo "/* time: O(n), space: O(n) */
export function $p_name_camel
  return
}" >$file_path
    echo "Success!"
  fi

  test_file_path=$dir_path/$p_name.test.ts
  if [ -f $test_file_path ]; then
    echo "File $test_file_path already exists"
    exit 1
  else
    p_number=$(echo "$p_name" | sed 's@^[^0-9]*\([0-9]\+\).*@\1@')
    echo "import { $p_name_camel } from \"./$p_name\";

test(\"problem $p_number\", () => {
  expect($p_name_camel()).toEqual();
  expect($p_name_camel()).toEqual();
  expect($p_name_camel()).toEqual();
  expect($p_name_camel()).toEqual();
});" >$test_file_path
    echo "Success!"
  fi

fi
