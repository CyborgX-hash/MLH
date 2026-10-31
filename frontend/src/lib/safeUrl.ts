// Every external link DeciTrace shows points at GitHub. Anything else (javascript:, data:, other hosts) is
// refused, so data from an untrusted source can never turn into an executable or misleading link.
export function isSafeGithubUrl(url: string | null | undefined): url is string {
  return typeof url === 'string' && /^https:\/\/github\.com\//i.test(url)
}
