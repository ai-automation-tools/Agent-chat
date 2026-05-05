// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
  site: 'https://docs.agent-chat.mikesailab.com',
  integrations: [
    starlight({
      title: 'Agent Chat',
      description:
        'A local MCP server that lets two CLI agents hold structured conversations with each other.',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/michaelschecht/Agent-chat',
        },
      ],
      sidebar: [
        { label: 'Overview', slug: '' },
        { label: 'Initial setup', slug: 'initial-setup' },
        {
          label: 'Hosting',
          items: [
            { label: 'Overview', slug: 'hosting' },
            { label: 'Fly.io deploy', slug: 'fly-deploy' },
          ],
        },
        { label: 'Roadmap', slug: 'roadmap' },
        { label: 'Changelog', slug: 'changelog' },
        {
          label: 'CLIs',
          items: [{ label: 'Gemini CLI', slug: 'clis/gemini' }],
        },
      ],
    }),
  ],
});
