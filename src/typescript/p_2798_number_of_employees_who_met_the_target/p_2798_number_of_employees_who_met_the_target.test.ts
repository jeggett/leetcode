import { numberOfEmployeesWhoMetTarget } from "./p_2798_number_of_employees_who_met_the_target.js";

test("problem 2798", () => {
  expect(numberOfEmployeesWhoMetTarget([1, 2, 0, 4, 5], 2)).toEqual(3);
  expect(numberOfEmployeesWhoMetTarget([1, 2, 5], 2)).toEqual(2);
});
