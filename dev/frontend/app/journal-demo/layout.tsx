import { MantineProvider } from "@mantine/core";

import "@mantine/core/styles.css";
import "@gfazioli/mantine-book/styles.css";

export default function JournalDemoLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <MantineProvider>{children}</MantineProvider>;
}
