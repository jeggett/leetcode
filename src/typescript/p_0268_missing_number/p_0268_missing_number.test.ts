import { missingNumber, missingNumberHashMap } from "./p_0268_missing_number.js";

test("problem 0268", () => {
    expect(missingNumber([3, 0, 1])).toEqual(2);
    expect(missingNumber([0, 1])).toEqual(2);
    expect(missingNumber([9, 6, 4, 2, 3, 5, 7, 0, 1])).toEqual(8);

    expect(missingNumberHashMap([0, 1, 2, 3, 5])).toEqual(4);
    expect(missingNumberHashMap([0, 1])).toEqual(2);
});
