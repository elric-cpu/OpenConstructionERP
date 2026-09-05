import { describe, expect, it } from "vitest";

import { createClientOperationId } from "./clientOperationId";

describe("createClientOperationId", () => {
  it("uses the platform UUID implementation when available", () => {
    const expected = "12345678-1234-4abc-8def-1234567890ab" as const;
    expect(createClientOperationId({
      getRandomValues: (array) => array,
      randomUUID: () => expected,
    })).toBe(expected);
  });

  it("creates an RFC 4122 version 4 UUID on non-secure development origins", () => {
    const source = {
      getRandomValues: <T extends Exclude<BufferSource, ArrayBuffer>>(array: T) => {
        if (array instanceof Uint8Array) {
          array.set([0, 1, 2, 3, 4, 5, 255, 7, 255, 9, 10, 11, 12, 13, 14, 15]);
        }
        return array;
      },
    };

    expect(createClientOperationId(source)).toBe("00010203-0405-4f07-bf09-0a0b0c0d0e0f");
  });
});
