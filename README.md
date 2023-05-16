# leetcode
Repo created to track progress on leetcode

 How to scaffold a new problem in its' own branch with init.sh

## Description

`init.sh` is a shell script that creates a new git branch, a directory with a two files inside: for the  problem itself and for the tests

## Usage

```bash
./init.sh <language> <problem_name>
```

Where `<language>` is either py for Python or ts for TypeScript; all the args after goes into 
`<problem_name>`. For example:

```bash
./init.sh ts 1512. Number of Good Pairs
```

will create a branch `feat/1512-number-of-good-pairs`,  and files: `src/typescript/1512NumberOfGoodPairs.ts`, `src/typescript/1512NumberOfGoodPairs.test.ts`
