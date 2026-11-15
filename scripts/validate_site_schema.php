#!/usr/bin/env php
<?php
/**
 * Run the site SchemaValidator against one or more exam JSON files.
 * No Laravel boot, no database. Passes the schema array into the constructor.
 *
 * Usage:
 *   php scripts/validate_site_schema.php \
 *     --schema reference/site-format/v2/question.schema.json \
 *     --validator /path/to/app/Support/SiteFormat/SchemaValidator.php \
 *     file.json [file.json ...]
 */
$schemaPath = null;
$validatorPath = null;
$files = [];
$args = array_slice($argv, 1);
for ($i = 0; $i < count($args); $i++) {
    if ($args[$i] === '--schema' && isset($args[$i + 1])) {
        $schemaPath = $args[++$i];
    } elseif ($args[$i] === '--validator' && isset($args[$i + 1])) {
        $validatorPath = $args[++$i];
    } elseif ($args[$i] === '--help' || $args[$i] === '-h') {
        fwrite(STDERR, "Usage: php validate_site_schema.php --schema SCHEMA --validator SchemaValidator.php FILE...\n");
        exit(2);
    } else {
        $files[] = $args[$i];
    }
}
if ($schemaPath === null || $validatorPath === null || $files === []) {
    fwrite(STDERR, "error: --schema, --validator and at least one file are required\n");
    exit(2);
}
if (! is_file($schemaPath) || ! is_file($validatorPath)) {
    fwrite(STDERR, "error: schema or validator file not found\n");
    exit(2);
}
require $validatorPath;

$schema = json_decode((string) file_get_contents($schemaPath), true, 512, JSON_THROW_ON_ERROR);
$validator = new App\Support\SiteFormat\SchemaValidator($schema);
$failed = 0;
$passed = 0;
$questions = 0;
foreach ($files as $file) {
    if (! is_file($file)) {
        fwrite(STDERR, "FAIL $file (not found)\n");
        $failed++;
        continue;
    }
    $doc = json_decode((string) file_get_contents($file), true, 512, JSON_THROW_ON_ERROR);
    $n = is_array($doc['questions'] ?? null) ? count($doc['questions']) : 0;
    $questions += $n;
    $errors = $validator->errors($doc);
    if ($errors === []) {
        $passed++;
        echo "PASS $file ($n questions)\n";
    } else {
        $failed++;
        echo "FAIL $file (".count($errors)." issues, $n questions)\n";
        foreach (array_slice($errors, 0, 20) as $e) {
            echo "  - $e\n";
        }
    }
}
echo "summary pass=$passed fail=$failed files=".count($files)." questions=$questions\n";
exit($failed === 0 ? 0 : 1);
