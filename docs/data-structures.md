# Lists and trees: TypeScript ↔ Python

These are the only bundled data structures. Start with the node classes: their fields and
constructor defaults match LeetCode and are small enough to reproduce on a whiteboard.

| Purpose | TypeScript | Python |
| --- | --- | --- |
| `ListNode(val = 0, next = null/None)` | [linked_list.ts](../src/typescript/data_structures/linked_list.ts) | [linked_list.py](../src/python/data_structures/linked_list.py) |
| `TreeNode(val = 0, left = null/None, right = null/None)` | [tree.ts](../src/typescript/data_structures/tree.ts) | [tree.py](../src/python/data_structures/tree.py) |
| List conversions | [`listFromArray`, `listToArray`](../src/typescript/data_structures/helpers.ts) | [`list_from_array`, `list_to_array`](../src/python/data_structures/helpers.py) |
| Tree conversions | [`treeFromLevelOrder`, `treeToLevelOrder`](../src/typescript/data_structures/helpers.ts) | [`tree_from_level_order`, `tree_to_level_order`](../src/python/data_structures/helpers.py) |

List building uses a dummy head and advances a tail pointer. It does not modify the input array.
List conversion walks `next` until `null`/`None`; input lists must be acyclic.

Trees use LeetCode level order: `[1, null, 2, 3]` means root `1`, no left child, right child `2`,
and `2`'s left child `3`. Missing parents have no child slots. Builders expect a valid level-order
sequence. Serializers trim trailing missing entries. Empty structures serialize to `[]`.

All conversions take O(n) time and O(n) space including their result. Tree queues advance an
index instead of removing the first element, so every queue entry is processed once.

## Tests

```ts
import { listFromArray, listToArray } from "../data_structures/helpers.js";

expect(listToArray(reverseList(listFromArray([1, 2, 3])))).toEqual([3, 2, 1]);
```

```python
from src.python.data_structures.helpers import list_from_array, list_to_array

assert list_to_array(Solution().reverseList(list_from_array([1, 2, 3]))) == [3, 2, 1]
```

TypeScript solutions use ambient judge types from `judge-types.d.ts`. If a solution constructs
new nodes at runtime, install the local class in the test (`vi.stubGlobal("ListNode", ListNode)`
and `vi.unstubAllGlobals()` in cleanup). In Python tests, import the solution module and use
`monkeypatch.setattr(solution_module, "ListNode", ListNode, raising=False)`. `TreeNode` works
the same way. Keep these local bindings in tests; LeetCode provides the classes on submission.
Python node annotations use postponed evaluation (`from __future__ import annotations`).
