/* time: O(n^2), space: O(1) */
export function countPairs(nums: number[], target: number): number {
    let count = 0;
    for (let i = 0; i < nums.length; i++) {
        for (let j = i + 1; j < nums.length; j++) {
            if (nums[i] + nums[j] < target) {
                count += 1;
            }
        }
    }
    return count;
}

// TODO solve later with in place sort and two pointers in O(n*log(n))
