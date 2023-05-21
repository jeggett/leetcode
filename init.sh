#!/bin/bash

# take language from the first argument
lang=$1
shift # remove the first argument

# join the remaining arguments with hyphens, remove dots, convert to lower case
p_name=p-$(echo "$@" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-')

git fetch origin main:main

branch_name=feat/$p_name
if git show-ref --quiet refs/heads/$branch_name; then
  echo "Branch $branch_name already exists"
  exit 1
else
  git checkout -b $branch_name main
fi

# replace - with _
p_name=${p_name//-/_}

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
    def main(self, args: List[int]) -> int:
        pass" >$file_path
  fi

  test_file_path=$dir_path/test_$p_name.py
  if [ -f $test_file_path ]; then
    echo "File $test_file_path already exists"
    exit 1
  else
    echo "from $p_name import Solution

solution = Solution()


def test_$p_name():
    assert solution.main() == 0" >$test_file_path
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
  p_name_camel=$(echo "$p_name" | sed -r 's/_(.)/\U\1/g')
  if [ -f $file_path ]; then
    echo "File $file_path already exists"
    exit 1
  else
    echo "export function $p_name_camel() {
  // write your code here
  return undefined;
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
  expect($p_name_camel(0)).toEqual(1);
});" >$test_file_path
    echo "Success!"
  fi

fi
