/* time: O(n), space: O(1) */
export function removeElement(nums: number[], val: number): number {
    let leftIndex = 0;
    let rightIndex = nums.length - 1;

    while (leftIndex <= rightIndex) {
        if (nums[leftIndex] === val) {
            nums[leftIndex] = nums[rightIndex];
            rightIndex--;
        } else {
            leftIndex++;
        }
    }

    return leftIndex;
}
