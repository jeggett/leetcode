import { createHelloWorld } from "./p_2667_create_hello_world_function";

test("problem 2667", () => {
  expect(createHelloWorld()(0, {})).toEqual("Hello World");
});
