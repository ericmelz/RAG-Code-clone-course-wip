// ChatBotPage.tsx
import ChatBot, { type Params } from "react-chatbotify";
import { Box, FormControl, InputLabel, Select, Typography, MenuItem, useMediaQuery } from '@mui/material';
import type { SelectChangeEvent } from '@mui/material/Select';
import { useState, useEffect, useMemo } from 'react';
import IndexingAPI from 'api/indexing';
import ChatAPI from 'api/chat';

/**
 * Interface representing an indexed GitHub repository.
 */
interface IndexedRepo {
    github_url: string;
    namespace: string;
    indexed_at: string;
}

/**
 * Chatbot page component for interacting with indexed GitHub repositories.
 * 
 * Features:
 * - Dropdown to select from previously indexed repositories
 * - Interactive chatbot that can answer questions about the selected repository
 * - Uses RAG (Retrieval-Augmented Generation) to provide contextual responses
 * 
 * The component loads all indexed repositories on mount and allows users to
 * chat about the selected repository's codebase.
 * 
 * @returns JSX element containing the repository selector and chatbot interface
 */
export default function ChatBotPage() {
    const [repos, setRepos] = useState<IndexedRepo[]>([]);
    const [selectedNamespace, setSelectedNamespace] = useState('');
    const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)');


    useEffect(() => {
        const loadRepos = async () => {
            try {
                const response = await IndexingAPI.getIndexedRepos();
                setRepos(response.repos);
                console.log(response.repos)
            } catch (error) {
                console.error('Error loading repos:', error);
            }
        };
        loadRepos();
    }, []);

    useEffect(() => {
        if (!selectedNamespace && repos.length > 0) {
            setSelectedNamespace(repos[0].namespace);
        }
    }, [repos, selectedNamespace]);

    const settings = {
        general: {
            embedded: true, showFooter: false, showHeader: false
        },
    }

    const darkStyles = useMemo(() => prefersDarkMode ? {
        chatWindowStyle: { width: 800, backgroundColor: '#1e1e1e' },
        bodyStyle: { backgroundColor: '#1e1e1e' },
        chatInputContainerStyle: { backgroundColor: '#2d2d2d', borderTop: '1px solid rgba(255,255,255,0.12)' },
        chatInputAreaStyle: { backgroundColor: '#2d2d2d', color: 'rgba(255,255,255,0.87)' },
        chatHistoryButtonStyle: { backgroundColor: '#2d2d2d', color: 'rgba(255,255,255,0.87)', border: '1px solid rgba(255,255,255,0.2)' },
        botBubbleStyle: { backgroundColor: '#3d3d3d', color: 'rgba(255,255,255,0.87)' },
        userBubbleStyle: { backgroundColor: '#1565c0', color: '#fff' },
    } : { chatWindowStyle: { width: 800 } }, [prefersDarkMode])

    /**
     * Handle user input from the chatbot and send it to the backend API.
     *
     * @param params - Parameters from the chatbot containing user input
     * @returns Promise resolving to the bot's response message
     */
    const handleUserInput = async (params: Params) => {
        try {
            if (!selectedNamespace) {
                return "Please select a GitHub repo from the dropdown menu above first.";
            }

            const response = await ChatAPI.sendMessages({
                message: params.userInput,
                namespace: selectedNamespace,
                userName: 'test_id'
            });

            return response.response || "I'm sorry, I couldn't process your request.";
        } catch (error) {
            console.error('Chat API error:', error);
            return "Sorry, there was an error processing your request. Please try again.";
        }
    }

    const handleSelectChange = (event: SelectChangeEvent<string>) => {
        setSelectedNamespace(event.target.value as string);
    };

    const flow = {
        start: {
            message: "Hello! I can help you with questions about a Github Repo. Please select a repository from the dropdown above to get started.",
            path: "chat_loop"
        },
        chat_loop: {
            message: handleUserInput,
            path: "chat_loop"
        }
    }

    return (
        <Box sx={{
            width: '100%', display: 'flex',
            flexDirection: 'column', alignItems: 'center',
            gap: 2, padding: 2
        }}>
            <Box sx={{ width: '100%', maxWidth: 600 }}>
                <Typography variant="h6" gutterBottom>
                    Select Gihub Repo
                </Typography>
                <FormControl fullWidth>
                    <InputLabel>Choose a Repo</InputLabel>
                    <Select
                        value={selectedNamespace}
                        label="Choose a Repo"
                        onChange={handleSelectChange}
                        disabled={repos.length === 0}
                    >
                        {repos.length === 0 && (
                            <MenuItem value="" disabled>
                                <em>No indexed repositories found</em>
                            </MenuItem>
                        )}
                        {repos?.map((repo) => (
                            <MenuItem
                                key={repo.namespace}
                                value={repo.namespace}>
                                <Box>
                                    <Typography variant="body1">
                                        {repo.github_url}
                                    </Typography>
                                    <Typography
                                        variant="caption"
                                        color="text.secondary">
                                        Indexed {new Date(repo.indexed_at).toLocaleDateString()}
                                    </Typography>
                                </Box>
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                <ChatBot
                    settings={settings}
                    styles={darkStyles}
                    flow={flow}
                />
            </Box>
        </Box>
    )
}
