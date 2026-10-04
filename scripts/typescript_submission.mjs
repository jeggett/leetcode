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

function typescriptSubmission(source) {
    let ast;
    try {
        ast = parse(source, {
            sourceType: "module",
            plugins: ["typescript"],
            createImportExpressions: true,
            allowUndeclaredExports: true,
            attachComment: false,
        });
    } catch (error) {
        throw new Error(`invalid TypeScript syntax: ${error.message}`);
    }

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

try {
    process.stdout.write(typescriptSubmission(readFileSync(0, "utf8")));
} catch (error) {
    console.error(error.message);
    process.exitCode = 1;
}
