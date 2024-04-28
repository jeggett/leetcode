/* time: O(n^2), space: O(1) */
const getMin = (nums: number[]): number => {
    let currentMinIndex = 0;
    for (let i = 1; i < nums.length; i++) {
        if (nums[i] < nums[currentMinIndex]) {
            currentMinIndex = i;
        }
    }
    return nums.splice(currentMinIndex, 1)[0];
};

export function numberGame(nums: number[]): number[] {
    const result: number[] = [];
    while (nums.length > 0) {
        result.push(...[getMin(nums), getMin(nums)].reverse());
    }

    return result;
}
