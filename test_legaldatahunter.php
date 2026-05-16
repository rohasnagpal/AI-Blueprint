<?php

$url = "https://legaldatahunter.com/v1/search";
$apiKey = "sk-jKc3NQmc0lMwp3KqEldTjqfzVq8LCZoKDmyF6bv7-VM";

$requestData = [
    "q" => "right to be forgotten",
    "namespace" => "case_law"
];

$ch = curl_init($url);

curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => json_encode($requestData),
    CURLOPT_HTTPHEADER => [
        "Authorization: Bearer " . $apiKey,
        "Content-Type: application/json"
    ],
    CURLOPT_SSL_VERIFYPEER => false,
    CURLOPT_SSL_VERIFYHOST => false
]);

$response = curl_exec($ch);
$error = curl_error($ch);

if ($error) {
    die("cURL Error: " . $error);
}

$data = json_decode($response, true);

if (!$data || !isset($data['hits'])) {
    die("Invalid API response");
}

?>
<!DOCTYPE html>
<html>
<head>
    <title>Legal Data Hunter Search</title>
</head>
<body>
    <h2>Search Results</h2>

    <?php foreach ($data['hits'] as $hit): ?>
        <div style="padding:15px;border:1px solid #ccc;margin:10px;border-radius:8px;">
            <h3><?= htmlspecialchars($hit['title'] ?? 'No Title') ?></h3>
            <p><strong>Court:</strong> <?= htmlspecialchars($hit['court'] ?? 'N/A') ?></p>
            <p><strong>Date:</strong> <?= htmlspecialchars($hit['date'] ?? 'N/A') ?></p>
            <p>
                <a href="<?= htmlspecialchars($hit['url'] ?? '#') ?>" target="_blank">
                    Open Case
                </a>
            </p>
        </div>
    <?php endforeach; ?>

</body>
</html>