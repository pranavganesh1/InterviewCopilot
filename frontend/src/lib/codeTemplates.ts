export type CodeLanguage = "python" | "java" | "c";

export const LANGUAGE_TABS: { id: CodeLanguage; label: string; monaco: string }[] =
  [
    { id: "python", label: "Python", monaco: "python" },
    { id: "java", label: "Java", monaco: "java" },
    { id: "c", label: "C", monaco: "c" },
  ];

export const STARTER_CODE: Record<CodeLanguage, string> = {
  python: `def solve():
    # Write your solution here
    pass


if __name__ == "__main__":
    print(solve())
`,
  java: `public class Solution {
    public static void main(String[] args) {
        System.out.println(solve());
    }

    static String solve() {
        // Write your solution here
        return "";
    }
}
`,
  c: `#include <stdio.h>

int solve(void) {
    /* Write your solution here */
    return 0;
}

int main(void) {
    printf("%d\\n", solve());
    return 0;
}
`,
};

export function formatCodeAnswer(language: CodeLanguage, code: string): string {
  const label =
    language === "python" ? "Python" : language === "java" ? "Java" : "C";
  return `Language: ${label}\n\n\`\`\`${language}\n${code.trimEnd()}\n\`\`\``;
}
