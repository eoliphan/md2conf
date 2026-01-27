<!-- confluence-page-id: 00000000000 -->

## Bash Code with Dollar Signs

This test ensures that bash variables with dollar signs are not mistaken for LaTeX formulas.

### Fenced Code Block

```bash
#!/bin/bash

BRANCH="feature/test"

if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "develop" ]; then
    echo "Building branch: $BRANCH"
    export VERSION="1.0.0"
    echo "Version: $VERSION"
fi

# Multiple dollar signs in one line
TEST="$VAR1 $VAR2 $VAR3"

# Dollar signs with special characters
PATH="$HOME/bin:$PATH"
FILE="${PROJECT_ROOT}/data/${ENVIRONMENT}.json"
```

### Inline Code

You can use `$BRANCH` and `$VERSION` variables in bash scripts.

### Mixed with LaTeX

Bash code: `$BRANCH`

LaTeX formula: \(x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}\)

More bash:

```bash
echo "Value: $MY_VAR"
```

More LaTeX:

\[E = mc^2\]
