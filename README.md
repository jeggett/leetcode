# leetcode

Leetcode solutions

`init.sh` is a shell script that creates a new git branch, a directory with a two files inside: for the problem itself and for the tests

## Usage

```bash
./init.sh <language> <problem_name>
```

Where `<language>` is either `py` for Python or `ts` for TypeScript; all the args after that go into
`<problem_name>`. For example:

```bash
./init.sh ts 1512. Number of Good Pairs
```

will create a branch `feat/1512-number-of-good-pairs`, and files:
`src/typescript/p_1512_number_of_good_pairs.ts`,
`src/typescript/p_1512_number_of_good_pairs.test.ts`
