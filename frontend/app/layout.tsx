import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'AI App Builder (MVP)',
  description: 'Describe the web app you want and get a generated static app.',
};

import './globals.css';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );
}
