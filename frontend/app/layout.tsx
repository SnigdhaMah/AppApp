import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'App² — a social network of microapps',
  description: 'Describe the app you want. We generate it for you.',
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
