export function leftRightDifference(nums: number[]): number[] {
  const sum: number = nums.reduce((acc, curr) => acc + curr);
  let rightSum = sum;
  let leftSum = 0;
  const answer: number[] = nums.map((num) => {
    rightSum -= num;
    const result = Math.abs(leftSum - rightSum);
    leftSum += num;
    return result;
  });
  return answer;
}
