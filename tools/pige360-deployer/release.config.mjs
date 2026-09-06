const repositoryUrl = process.env.REPOSITORY_URL
  || (process.env.GITHUB_SERVER_URL && process.env.GITHUB_REPOSITORY
    ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}.git`
    : undefined);

const config = {
  branches: ['main'],
  tagFormat: 'v${version}',
  plugins: [
    '@semantic-release/commit-analyzer',
    '@semantic-release/release-notes-generator',
    ['@semantic-release/changelog', { changelogFile: 'CHANGELOG.md' }],
    ['@semantic-release/exec', {
      prepareCmd: 'node ./scripts/release/prepare-release.mjs ${nextRelease.version}'
    }],
    ['@semantic-release/git', {
      assets: [
        'VERSION',
        'package.json',
        'package-lock.json',
        'src-tauri/Cargo.toml',
        'src-tauri/Cargo.lock',
        'src-tauri/tauri.conf.json',
        'src/config/projectConfig.ts',
        'CHANGELOG.md'
      ],
      message: 'chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}'
    }]
  ]
};

if (repositoryUrl) {
  config.repositoryUrl = repositoryUrl;
}

export default config;
