// time O(n), space O(1)
export function productExceptSelf(nums: number[]): number[] {
  const result: number[] = [1];
  for (let i = 0; i < nums.length - 1; i++) {
    result[i + 1] = result[i] * nums[i];
  }
  let runningProduct = 1;
  for (let i = nums.length - 1; i > 0; i--) {
    result[i - 1] *= runningProduct *= nums[i];
  }

  return result;
}
