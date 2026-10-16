import { TreeNode, treeFromLevelOrder, treeToLevelOrder } from "./tree.js";

test("node defaults and links match LeetCode", () => {
    expect(new TreeNode()).toEqual({ val: 0, left: null, right: null });
    const child = new TreeNode(2);
    expect(new TreeNode(1, child, child).right).toBe(child);
});

test.each([
    { input: [], expected: [] },
    { input: [null], expected: [] },
    { input: [0], expected: [0] },
    { input: [1, 1, 1], expected: [1, 1, 1] },
    { input: [1, null, 2, 3, null, null, 4], expected: [1, null, 2, 3, null, null, 4] },
    { input: [1, 2, null, null, 3, null, null], expected: [1, 2, null, null, 3] },
])("tree round trip: $input", ({ input, expected }) => {
    const root = treeFromLevelOrder(Object.freeze(input));
    expect(treeToLevelOrder(root)).toEqual(expected);
    expect(treeToLevelOrder(treeFromLevelOrder(treeToLevelOrder(root)))).toEqual(expected);
});

test("level-order positions follow parents with children", () => {
    const root = treeFromLevelOrder([1, null, 2, 3]);
    expect(root?.left).toBeNull();
    expect(root?.right?.left?.val).toBe(3);
});
