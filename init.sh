#!/bin/bash

# take language from the first argument
lang=$1
shift # remove the first argument

# join the remaining arguments with hyphens, remove dots, convert to lower case
problem_name=problem-$(echo "$@" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-') 

git remote update

branch_name=feat/$problem_name
if git show-ref --quiet refs/heads/$branch_name;  then
  echo "Branch $branch_name already exists"
  exit 1
else
  git checkout -b $branch_name main #branch from up to date 'main'
fi

if [ $lang == "py" ]; then

  # replace - with _
  problem_name=${problem_name//-/_}

  dir_path=src/python/$problem_name 
  if [ -d $dir_path ]; then # check if directory already exists
    echo "Directory $dir_path already exists"
    exit 1
  else
    mkdir -p $dir_path
  fi

  # create .py file for a problem itself
  file_path=$dir_path/$problem_name.py 
  if [ -f $file_path ]; then 
    echo "File $file_path already exists"
    exit 1
  else
    echo "class Solution():
    def main(self):
        # write your code here
        pass" > $file_path
  fi

  # create .py file for a test
  test_file_path=$dir_path/test_$problem_name.py # assign test file path to a variable
  if [ -f $test_file_path ]; then
    echo "File $test_file_path already exists"
    exit 1
  else 
    echo "import pytest
from $problem_name import Solution


def test_main():
    sol = Solution()
    assert sol.main() == None" > $test_file_path 
    echo "Success!"
  fi

elif [ $lang == "ts" ]; then

  # change contents of the variable problem_name from kebab-case to camelCase
  problem_name=$(echo $problem_name | sed -r 's/-(.)/\U\1/g')

  dir_path=src/typescript/$problem_name 
  if [ -d $dir_path ]; then 
    echo "Directory $dir_path already exists"
    exit 1 
  else 
    mkdir -p $dir_path 
  fi 

  file_path=$dir_path/$problem_name.ts 
  if [ -f $file_path ]; then 
    echo "File $file_path already exists"
    exit 1 
  else 
    echo "export function main() {
      // write your code here
      return;
    }" > $file_path 
    echo "Success!"
  fi
fi
