/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: true,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "dnznrvs05pmza.cloudfront.net"
      }
    ]
  },
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb"
    }
  }
};

export default nextConfig;
