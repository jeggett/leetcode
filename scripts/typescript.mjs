import { readFileSync } from "node:fs";
import { parse } from "@babel/parser";

function* nodes(value) {
    if (Array.isArray(value)) {
        for (const child of value) yield* nodes(child);
    } else if (value && typeof value.type === "string") {
        yield value;
        for (const child of Object.values(value)) yield* nodes(child);
    }
}

function isMember(node, object, property) {
    return (
        ["MemberExpression", "OptionalMemberExpression"].includes(node.type) &&
        node.object.type === "Identifier" &&
        node.object.name === object &&
        (property === undefined ||
            (node.computed
                ? node.property.type === "StringLiteral" && node.property.value === property
                : node.property.name === property))
    );
}

function parseTypeScript(source) {
    try {
        return parse(source, {
            sourceType: "module",
            plugins: ["typescript"],
            createImportExpressions: true,
            allowUndeclaredExports: true,
            attachComment: false,
            tokens: true,
        });
    } catch (error) {
        throw new Error(`invalid TypeScript syntax: ${error.message}`);
    }
}

function typescriptSubmission(source) {
    const ast = parseTypeScript(source);
    for (const comment of ast.comments) {
        if (
            comment.type === "CommentLine" &&
            /^\/[ \t]*<reference(?:[ \t/>]|$)/.test(comment.value)
        ) {
            throw new Error("TypeScript submission contains a triple-slash reference directive");
        }
    }

    for (const node of nodes(ast.program)) {
        if (
            [
                "ImportDeclaration",
                "ImportExpression",
                "TSImportType",
                "TSImportEqualsDeclaration",
            ].includes(node.type) ||
            (node.type === "MetaProperty" && node.meta.name === "import")
        ) {
            throw new Error(
                "TypeScript submission contains an import and cannot be self-contained",
            );
        }
        if (
            ["CallExpression", "OptionalCallExpression"].includes(node.type) &&
            node.callee.type === "Identifier" &&
            node.callee.name === "require"
        ) {
            throw new Error(
                "TypeScript submission contains a CommonJS require and cannot be self-contained",
            );
        }
        if (
            isMember(node, "module", "exports") ||
            isMember(node, "exports") ||
            (node.type === "AssignmentExpression" &&
                node.left.type === "Identifier" &&
                node.left.name === "exports")
        ) {
            throw new Error(
                "TypeScript submission contains a CommonJS export and cannot be self-contained",
            );
        }
    }

    const declarations = new Set([
        "ClassDeclaration",
        "FunctionDeclaration",
        "VariableDeclaration",
        "TSTypeAliasDeclaration",
        "TSInterfaceDeclaration",
        "TSEnumDeclaration",
        "TSDeclareFunction",
    ]);
    const removals = [];
    for (const statement of ast.program.body) {
        if (
            !statement.type.startsWith("Export") &&
            !["TSExportAssignment", "TSNamespaceExportDeclaration"].includes(statement.type)
        )
            continue;
        if (
            statement.type !== "ExportNamedDeclaration" ||
            statement.source ||
            !declarations.has(statement.declaration?.type)
        ) {
            throw new Error("unsupported TypeScript export");
        }
        removals.push(statement.start);
    }
    for (const start of removals.reverse()) {
        source = source.slice(0, start) + source.slice(start + "export".length);
    }
    return source;
}

function typescriptSignature(source, extract) {
    const prefix = "function ";
    const code = extract ? source : `${prefix}${source} {}`;
    const ast = parseTypeScript(code);
    const fn = ast.program.body.find((node) => node.type === "FunctionDeclaration");
    if (!fn?.id || !fn.returnType || fn.async || fn.generator) {
        throw new Error("signature must describe an ordinary function with a return type");
    }
    if (
        !extract &&
        (ast.program.body.length !== 1 ||
            ast.comments.length ||
            fn.body.start !== prefix.length + source.length + 1)
    ) {
        throw new Error("invalid TypeScript function signature");
    }
    if (
        ast.comments.some(
            (comment) => comment.start >= fn.id.start && comment.start < fn.body.start,
        )
    ) {
        throw new Error("signature comments are unsupported");
    }
    // Normalize whitespace between tokens without changing string literal types.
    let signature = "";
    let previous = fn.id.start;
    for (const token of ast.tokens) {
        if (token.start < fn.id.start || token.end > fn.body.start) continue;
        signature += code.slice(previous, token.start).replace(/\s+/g, " ");
        signature += code.slice(token.start, token.end);
        previous = token.end;
    }
    if (extract) {
        const names = new Set(
            ast.tokens
                .filter((token) => token.start >= fn.id.end && token.end <= fn.body.start)
                .map((token) => token.value),
        );
        const required = ast.program.body.filter(
            (node) => node !== fn && node.id && names.has(node.id.name),
        );
        if (required.length) {
            throw new Error(
                `signature needs omitted declaration(s): ${required.map((node) => node.id.name).join(", ")}`,
            );
        }
    }
    return JSON.stringify([signature.trim(), fn.id.name]);
}

try {
    const source = readFileSync(0, "utf8");
    const operation = process.argv[2];
    if (operation === "submission") process.stdout.write(typescriptSubmission(source));
    else if (operation === "signature" || operation === "extract-signature") {
        process.stdout.write(typescriptSignature(source, operation === "extract-signature"));
    } else throw new Error(`unknown TypeScript operation: ${operation}`);
} catch (error) {
    console.error(error.message);
    process.exitCode = 1;
}
